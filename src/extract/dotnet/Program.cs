// sf-extract: extract Satisfactory building meshes from a local game install and
// write them as glTF binary (.glb), using CUE4Parse (the library behind FModel).
//
// Usage:
//   sf-extract --game-dir <SatisfactoryInstall> --out <dir> [asset ...]
//   sf-extract --game-dir <dir> --list buildings.txt --out models
//
// Asset paths are package paths WITHOUT extension, e.g.
//   FactoryGame/Content/FactoryGame/Buildable/Factory/ConstructorMk1/Mesh/SM_ConstructorMk1
//
// An asset (positional or list line) may pin its output .glb stem with "path = name":
//   .../SmelterMk1/Mesh/SmelterMk1_static = smelter   ->   models/smelter.glb
// Without an override the leaf name is used (SM_/SK_ prefix stripped).
//
// usmap + CustomVersions.json ship inside the game under CommunityResources/ and
// are auto-detected; override with --usmap / --custom-versions if needed.

using System.Text;
using System.Text.Json;
using CUE4Parse.Compression;
using CUE4Parse.FileProvider;
using CUE4Parse.MappingsProvider;
using CUE4Parse.UE4.Assets.Exports;
using CUE4Parse.UE4.Assets.Exports.SkeletalMesh;
using CUE4Parse.UE4.Assets.Exports.StaticMesh;
using CUE4Parse.UE4.Assets.Exports.Texture;
using CUE4Parse.UE4.Objects.Core.Math;
using CUE4Parse.UE4.Objects.Core.Misc;
using CUE4Parse.UE4.Objects.Core.Serialization;
using CUE4Parse.UE4.Objects.UObject;
using CUE4Parse.UE4.Versions;
using CUE4Parse_Conversion;
using CUE4Parse_Conversion.Meshes;
using Serilog;

var opts = Args.Parse(args);
if (opts is null) return 2;

// Surface CUE4Parse's internal warnings/errors (per-export deserialize failures are
// logged, not thrown). Without a sink these are silently swallowed.
Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Warning()
    .WriteTo.Console(standardErrorFromLevel: Serilog.Events.LogEventLevel.Verbose)
    .CreateLogger();

Directory.CreateDirectory(opts.OutDir);

// --- Decompression backends -------------------------------------------------
// Zlib/Zstd are cross-platform and managed/native-portable. Oodle is the sticky
// one: OodleHelper auto-downloads a prebuilt lib on Windows/Linux, uses the
// CUE4Parse-Natives dylib if it was built with Oodle, or a lib passed via --oodle.
try { ZlibHelper.Initialize(); } catch (Exception e) { Console.Error.WriteLine($"[warn] zlib init: {e.Message}"); }
try
{
    OodleHelper.Initialize(opts.OodlePath);
    Console.Error.WriteLine(OodleHelper.Instance is not null
        ? "[info] Oodle decompression ready."
        : "[warn] Oodle NOT initialized. Extraction will fail if the game's paks are Oodle-compressed.\n" +
          "        On macOS there is no prebuilt Oodle: run extraction in a linux/amd64 container,\n" +
          "        or pass --oodle <path-to-oodle-lib>.");
}
catch (Exception e) { Console.Error.WriteLine($"[warn] oodle init: {e.Message}"); }

// --- Build the Satisfactory file provider ----------------------------------
var archiveDir = ResolveArchiveDir(opts.GameDir);
var usmap = opts.UsmapPath ?? FindFile(opts.GameDir, "FactoryGame.usmap");
var customVersionsPath = opts.CustomVersionsPath ?? FindFile(opts.GameDir, "CustomVersions.json");
if (usmap is null)
    Console.Error.WriteLine("[warn] FactoryGame.usmap not found under game dir; UE5 assets may fail to parse.");

var customVersions = LoadCustomVersions(customVersionsPath);
Console.Error.WriteLine($"[info] usmap={usmap ?? "(none)"}");
Console.Error.WriteLine($"[info] customVersions={customVersionsPath ?? "(none)"} " +
    $"loaded={customVersions?.Versions.Length ?? 0} " +
    $"Dev-Rendering={customVersions?.GetVersion(new CUE4Parse.UE4.Objects.Core.Misc.FGuid("12F88B9F88754AFCA67CD90C383ABD29")) ?? -99}");

// Satisfactory 1.2.x (anniversary-2026) is a customized UE 5.6.1 build.
// UE5.6 package file version = 1017 (OS_SUB_OBJECT_SHADOW_SERIALIZATION); CUE4Parse's
// own EGame table maps < GAME_UE5_7 to FPackageFileVersion(522, 1017).
var versions = new VersionContainer(
    EGame.GAME_UE5_6,
    ETexturePlatform.DesktopMobile,
    ver: new FPackageFileVersion(522, (int) EUnrealEngineObjectUE5Version.OS_SUB_OBJECT_SHADOW_SERIALIZATION),
    customVersions: customVersions);

#pragma warning disable CS0618 // ctor overload is marked obsolete but is what relyen/FModel use for SF
var provider = new DefaultFileProvider(archiveDir, SearchOption.AllDirectories, true, versions);
#pragma warning restore CS0618

if (usmap is not null)
    provider.MappingsContainer = new FileUsmapTypeMappingsProvider(usmap);

provider.Initialize();
provider.Mount();
Console.Error.WriteLine($"[info] Mounted {provider.Files.Count:N0} files from {archiveDir}");

// --- Discovery mode ---------------------------------------------------------
// Asset paths drift between game versions; --find <substr> lists matching mounted
// files (case-insensitive) so you can copy real paths into buildings.txt. File
// listing comes from the pak/utoc index and does NOT require Oodle.
if (opts.Find is not null)
{
    var needle = opts.Find;
    var hits = provider.Files.Keys
        .Where(k => k.Contains(needle, StringComparison.OrdinalIgnoreCase))
        .OrderBy(k => k, StringComparer.OrdinalIgnoreCase)
        .ToList();
    Console.Error.WriteLine($"[find] {hits.Count} file(s) matching \"{needle}\":");
    foreach (var k in hits) Console.WriteLine(k);
    return 0;
}

// --- Port dump mode ---------------------------------------------------------
// Load Build_* blueprint packages and dump every connection component (belt =
// FGFactoryConnectionComponent, pipe = FGPipeConnection*), with RelativeLocation /
// RelativeRotation / direction. This is how we learn exact I/O port positions,
// which are NOT present in Docs/en-US.json (mFactory*Connections there are empty).
if (opts.DumpPorts)
{
    var all = new List<object>();
    foreach (var spec in opts.Assets)
    {
        var pkgPath = NormalizePackagePath(spec.Path);
        try
        {
            var exports = provider.LoadPackage(pkgPath).GetExports().ToList();
            var conns = exports
                .Where(e => e.ExportType.Contains("Connection", StringComparison.OrdinalIgnoreCase))
                .ToList();

            Console.Error.WriteLine($"[ports] {pkgPath}: {exports.Count} exports, {conns.Count} connection component(s)");
            if (conns.Count == 0)
                foreach (var t in exports.Select(e => e.ExportType).Distinct().OrderBy(x => x))
                    Console.Error.WriteLine($"[ports]   export type: {t}");

            var ports = new List<object>();
            foreach (var c in conns)
            {
                var loc = c.GetOrDefault<FVector>("RelativeLocation");
                var rot = c.GetOrDefault<FRotator>("RelativeRotation");
                var props = new Dictionary<string, string>();
                foreach (var p in c.Properties)
                    props[p.Name.Text] = p.Tag?.GenericValue?.ToString() ?? "null";
                ports.Add(new
                {
                    name = c.Name,
                    @class = c.ExportType,
                    loc = new[] { loc.X, loc.Y, loc.Z },
                    rot = new[] { rot.Pitch, rot.Yaw, rot.Roll },
                    props,
                });
            }

            // Also dump every component that carries a RelativeLocation and/or a mesh
            // reference. A mesh component's RelativeLocation/Rotation/Scale is the offset
            // between the mesh's local origin and the build/snap origin that ports and
            // clearance are expressed in -- needed to align a standalone-extracted mesh
            // (e.g. SM_HadronCollider_01, whose pivot is ~11 m off the root) to that frame.
            var components = new List<object>();
            foreach (var e in exports)
            {
                var hasLoc = e.Properties.Any(p => p.Name.Text == "RelativeLocation");
                var smProp = e.Properties.FirstOrDefault(
                    p => p.Name.Text == "StaticMesh" || p.Name.Text == "SkeletalMesh");
                if (!hasLoc && smProp is null) continue;
                var loc = e.GetOrDefault<FVector>("RelativeLocation");
                var rot = e.GetOrDefault<FRotator>("RelativeRotation");
                var scale = e.GetOrDefault<FVector>("RelativeScale3D", new FVector(1f, 1f, 1f));
                var meshRef = smProp?.Tag?.GenericValue?.ToString() ?? "";
                components.Add(new
                {
                    name = e.Name,
                    @class = e.ExportType,
                    mesh = meshRef,
                    loc = new[] { loc.X, loc.Y, loc.Z },
                    rot = new[] { rot.Pitch, rot.Yaw, rot.Roll },
                    scale = new[] { scale.X, scale.Y, scale.Z },
                });
            }
            Console.Error.WriteLine($"[ports]   {components.Count} component(s) with location/mesh");
            all.Add(new { asset = pkgPath, ports, components });
        }
        catch (Exception e)
        {
            Console.Error.WriteLine($"[ports][fail] {pkgPath}: {e.Message}");
        }
    }
    var json = JsonSerializer.Serialize(all, new JsonSerializerOptions { WriteIndented = true });
    var outFile = Path.Combine(opts.OutDir, "ports.raw.json");
    File.WriteAllText(outFile, json);
    Console.WriteLine(json);
    Console.Error.WriteLine($"[ports] wrote {outFile}");
    return 0;
}

// --- Export loop ------------------------------------------------------------
// Clean geometry only: glTF binary, first LOD, no materials/morphs/sockets.
var exportOptions = new ExporterOptions
{
    MeshFormat = EMeshFormat.Gltf2,
    LodFormat = ELodFormat.FirstLod,
    Platform = ETexturePlatform.DesktopMobile,
    SocketFormat = ESocketFormat.None,
    ExportMaterials = false,
    ExportMorphTargets = false,
};

int ok = 0, fail = 0;
var manifest = new List<object>();

foreach (var spec in opts.Assets)
{
    var pkgPath = NormalizePackagePath(spec.Path);
    // Explicit "assetPath = name" override lets buildings.txt pin the .glb stem to the
    // friendly key used by clearance.json / ports.json (e.g. SmelterMk1_static -> smelter),
    // so no manual rename step is needed after extraction.
    var name = spec.Name ?? SanitizeName(Path.GetFileName(pkgPath));
    try
    {
        var exports = provider.LoadPackage(pkgPath).GetExports().ToList();
        MeshExporter? exporter = null;

        if (exports.OfType<UStaticMesh>().FirstOrDefault() is { } sm)
        {
            var rd = sm.RenderData;
            var nanite = rd?.NaniteResources;
            Console.Error.WriteLine($"[diag] {name}: props={sm.Properties.Count} bCooked={sm.bCooked} " +
                $"RenderData={(rd is null ? "null" : "ok")} " +
                $"LODs={rd?.LODs?.Length ?? -1} Nanite={(nanite is null ? "null" : "present")} " +
                $"pages={nanite?.PageStreamingStates?.Length ?? -1}");
            if (rd?.LODs is { } lods)
                for (int li = 0; li < lods.Length; li++)
                    Console.Error.WriteLine($"[diag]   LOD{li} skip={lods[li].SkipLod} " +
                        $"verts={lods[li].PositionVertexBuffer?.Verts?.Length ?? -1}");
            exporter = new MeshExporter(sm, exportOptions);
        }
        else if (exports.OfType<USkeletalMesh>().FirstOrDefault() is { } skm)
            exporter = new MeshExporter(skm, exportOptions);

        var glb = exporter?.MeshLods.FirstOrDefault()?.FileData;

        if (glb is null || glb.Length == 0)
        {
            var kinds = string.Join(", ", exports.Select(e => e.GetType().Name).Distinct());
            var why = exporter is null ? "no UStaticMesh/USkeletalMesh export" : "mesh had no exportable LODs";
            Console.Error.WriteLine($"[skip] {pkgPath}: {why}. exports=[{kinds}]");
            fail++;
            continue;
        }

        var outPath = Path.Combine(opts.OutDir, name + ".glb");
        File.WriteAllBytes(outPath, glb);
        Console.WriteLine($"[ok]  {name}.glb  ({glb.Length / 1024.0:F1} KB)");
        manifest.Add(new { name, asset = pkgPath, file = name + ".glb", bytes = glb.Length });
        ok++;
    }
    catch (Exception e)
    {
        Console.Error.WriteLine($"[fail] {pkgPath}: {e.Message}");
        fail++;
    }
}

File.WriteAllText(
    Path.Combine(opts.OutDir, "extracted.json"),
    JsonSerializer.Serialize(manifest, new JsonSerializerOptions { WriteIndented = true }));

Console.WriteLine($"\nDone: {ok} exported, {fail} failed -> {opts.OutDir}");
return fail > 0 && ok == 0 ? 1 : 0;


// ------------------------------------------------------------------ helpers --

static string ResolveArchiveDir(string gameDir)
{
    if (!Directory.Exists(gameDir))
        throw new DirectoryNotFoundException($"Game directory does not exist: {gameDir}");

    string[] candidates =
    [
        Path.Combine(gameDir, "FactoryGame", "Content", "Paks"),
        Path.Combine(gameDir, "FactoryGame", "Content"),
        gameDir
    ];

    foreach (var c in candidates)
    {
        if (Directory.Exists(c) &&
            (Directory.EnumerateFiles(c, "*.pak").Any()
             || Directory.EnumerateFiles(c, "*.utoc").Any()
             || Directory.EnumerateFiles(c, "*.ucas").Any()))
            return c;
    }

    throw new DirectoryNotFoundException(
        $"No .pak/.utoc/.ucas found under {gameDir} (expected FactoryGame/Content/Paks).");
}

static string? FindFile(string root, string fileName)
{
    if (!Directory.Exists(root)) return null;
    return Directory.EnumerateFiles(root, fileName, SearchOption.AllDirectories)
        .OrderBy(p => p.Length) // prefer the shallowest match
        .FirstOrDefault();
}

static FCustomVersionContainer? LoadCustomVersions(string? path)
{
    if (string.IsNullOrWhiteSpace(path) || !File.Exists(path)) return null;

    // CustomVersions.json ships as UTF-16 LE (sometimes without a BOM), which
    // File.ReadAllText mis-decodes as UTF-8 -> interleaved 0x00 -> JSON error.
    var text = ReadTextSmart(path);
    using var doc = JsonDocument.Parse(text, new JsonDocumentOptions
    {
        AllowTrailingCommas = true,
        CommentHandling = JsonCommentHandling.Skip
    });

    if (doc.RootElement.ValueKind != JsonValueKind.Array) return null;

    var versions = new List<FCustomVersion>();
    foreach (var el in doc.RootElement.EnumerateArray())
    {
        if (el.ValueKind != JsonValueKind.Object) continue;
        if (!el.TryGetProperty("Key", out var keyEl) || keyEl.ValueKind != JsonValueKind.String) continue;
        if (!el.TryGetProperty("Version", out var verEl) || !verEl.TryGetInt32(out var ver)) continue;

        var key = keyEl.GetString();
        if (string.IsNullOrWhiteSpace(key)) continue;
        var normalized = key.Replace("-", string.Empty);
        if (normalized.Length != 32 || !normalized.All(Uri.IsHexDigit)) continue;

        versions.Add(new FCustomVersion(new FGuid(normalized), ver));
    }

    return new FCustomVersionContainer(versions);
}

static string ReadTextSmart(string path)
{
    var bytes = File.ReadAllBytes(path);
    if (bytes.Length >= 2 && bytes[0] == 0xFF && bytes[1] == 0xFE)
        return Encoding.Unicode.GetString(bytes, 2, bytes.Length - 2);          // UTF-16 LE BOM
    if (bytes.Length >= 2 && bytes[0] == 0xFE && bytes[1] == 0xFF)
        return Encoding.BigEndianUnicode.GetString(bytes, 2, bytes.Length - 2); // UTF-16 BE BOM
    if (bytes.Length >= 3 && bytes[0] == 0xEF && bytes[1] == 0xBB && bytes[2] == 0xBF)
        return Encoding.UTF8.GetString(bytes, 3, bytes.Length - 3);             // UTF-8 BOM

    // No BOM: sniff for UTF-16 LE (lots of 0x00 bytes, common in Satisfactory's file).
    int zeros = 0, n = Math.Min(bytes.Length, 64);
    for (int i = 0; i < n; i++) if (bytes[i] == 0) zeros++;
    return zeros > n / 4 ? Encoding.Unicode.GetString(bytes) : Encoding.UTF8.GetString(bytes);
}

static string NormalizePackagePath(string asset)
{
    var p = asset.Replace('\\', '/').Trim();
    // strip a trailing .uasset/.uexp/.umap if the user pasted a full file path
    foreach (var ext in new[] { ".uasset", ".umap", ".uexp" })
        if (p.EndsWith(ext, StringComparison.OrdinalIgnoreCase))
            p = p[..^ext.Length];
    return p;
}

static string SanitizeName(string leaf)
{
    if (leaf.StartsWith("SM_", StringComparison.OrdinalIgnoreCase) ||
        leaf.StartsWith("SK_", StringComparison.OrdinalIgnoreCase))
        leaf = leaf[3..];
    return leaf;
}


file sealed record AssetSpec(string Path, string? Name);

file sealed record Args(
    string GameDir,
    string OutDir,
    string? UsmapPath,
    string? CustomVersionsPath,
    string? OodlePath,
    string? Find,
    bool DumpPorts,
    IReadOnlyList<AssetSpec> Assets)
{
    // A list/positional entry may pin the output name: "assetPath = friendlyName".
    private static AssetSpec ParseSpec(string entry)
    {
        var eq = entry.IndexOf('=');
        if (eq < 0) return new AssetSpec(entry.Trim(), null);
        var path = entry[..eq].Trim();
        var name = entry[(eq + 1)..].Trim();
        return new AssetSpec(path, name.Length > 0 ? name : null);
    }

    public static Args? Parse(string[] argv)
    {
        string? gameDir = null, outDir = "models", usmap = null, custom = null, oodle = null, listFile = null, find = null;
        bool dumpPorts = false;
        var assets = new List<AssetSpec>();

        for (int i = 0; i < argv.Length; i++)
        {
            switch (argv[i])
            {
                case "--game-dir": gameDir = Next(argv, ref i); break;
                case "--out": outDir = Next(argv, ref i) ?? outDir; break;
                case "--usmap": usmap = Next(argv, ref i); break;
                case "--custom-versions": custom = Next(argv, ref i); break;
                case "--oodle": oodle = Next(argv, ref i); break;
                case "--list": listFile = Next(argv, ref i); break;
                case "--find": find = Next(argv, ref i); break;
                case "--dump-ports": dumpPorts = true; break;
                case "-h" or "--help": PrintUsage(); return null;
                default:
                    if (argv[i].StartsWith('-')) { Console.Error.WriteLine($"Unknown arg: {argv[i]}"); PrintUsage(); return null; }
                    assets.Add(ParseSpec(argv[i]));
                    break;
            }
        }

        if (listFile is not null && File.Exists(listFile))
            foreach (var line in File.ReadAllLines(listFile))
            {
                var l = line.Split('#', 2)[0].Trim();
                if (l.Length > 0) assets.Add(ParseSpec(l));
            }

        if (gameDir is null) { Console.Error.WriteLine("ERROR: --game-dir is required."); PrintUsage(); return null; }
        if (find is null && assets.Count == 0) { Console.Error.WriteLine("ERROR: no assets given (positional or --list)."); PrintUsage(); return null; }

        return new Args(gameDir, outDir!, usmap, custom, oodle, find, dumpPorts, assets);
    }

    private static string? Next(string[] a, ref int i) => i + 1 < a.Length ? a[++i] : null;

    private static void PrintUsage() => Console.Error.WriteLine(
        """
        sf-extract --game-dir <dir> [--out models] [--usmap x.usmap]
                   [--custom-versions CustomVersions.json] [--oodle <lib>]
                   [--list buildings.txt] [asset ...]
        """);
}
