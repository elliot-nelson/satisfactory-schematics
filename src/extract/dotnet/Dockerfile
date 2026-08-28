# Linux/amd64 runtime for sf-extract.
#
# Why a container? Satisfactory's paks are Oodle-compressed, and there is no prebuilt Oodle
# library for macOS. On Linux, CUE4Parse loads a prebuilt Oodle .so, so extraction "just works".
# We build for linux/amd64 (runs via Rosetta/qemu on Apple Silicon) to match the Oodle binary.
#
# The build CONTEXT is the repo root (see src/extract/run.py) because the C# app and its vendored
# CUE4Parse dependency live in two sibling trees (src/ and vendor/). We recreate the same
# repo-relative layout inside the image so the .csproj's ProjectReference (../../../vendor/...)
# resolves identically on the host and in the container.
FROM --platform=linux/amd64 mcr.microsoft.com/dotnet/sdk:10.0

ENV CUE4PARSE_SKIP_NATIVE=true

WORKDIR /work
COPY src/extract/dotnet /work/src/extract/dotnet
COPY vendor/cue4parse   /work/vendor/cue4parse

# Restore + build once at image-build time.
RUN dotnet build /work/src/extract/dotnet/sf-extract.csproj -c Release -p:CUE4PARSE_SKIP_NATIVE=true

# Bake the native decompression libs into the image. CUE4Parse would otherwise try to download
# these at runtime into the cwd and load them by bare name -- but dlopen("libz-ng.so") searches
# the loader path, NOT the cwd, so that fails. We fetch valid linux-x64 builds at image-build
# time and put them on LD_LIBRARY_PATH.
#   - libz-ng.so           : Zlib-ng.NET release (matches ZlibHelper.DOWNLOAD_URL_LINUX)
#   - liboodle-data-shared : WorkingRobot/OodleUE release (matches OodleHelper RELEASE_URL)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/nativelibs \
    && curl -fsSL https://github.com/NotOfficer/Zlib-ng.NET/releases/download/1.0.0/libz-ng.so.gz \
        | gzip -d > /opt/nativelibs/libz-ng.so \
    && curl -fsSL -o /tmp/oodle.zip \
        https://github.com/WorkingRobot/OodleUE/releases/download/2026-01-25-1223/gcc-x64-release.zip \
    && unzip -j /tmp/oodle.zip 'lib/liboodle-data-shared.so' -d /opt/nativelibs \
    && rm -f /tmp/oodle.zip \
    && chmod +x /opt/nativelibs/libz-ng.so /opt/nativelibs/liboodle-data-shared.so

ENV LD_LIBRARY_PATH=/opt/nativelibs

# Game files mount at /game, output at /out (see src/extract/run.py).
ENTRYPOINT ["dotnet", "/work/src/extract/dotnet/bin/Release/net10.0/sf-extract.dll"]
