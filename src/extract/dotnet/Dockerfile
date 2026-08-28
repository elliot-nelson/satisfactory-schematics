# Linux/amd64 runtime for sf-extract.
#
# Why a container? Satisfactory's paks are Oodle-compressed, and there is no
# prebuilt Oodle library for macOS. On Linux, CUE4Parse auto-downloads the Oodle
# .so at runtime, so extraction "just works". We build for linux/amd64 (runs via
# Rosetta/qemu on Apple Silicon) to match the available Oodle binary.
#
# Build context is the extractor/ dir (see .dockerignore - bin/obj excluded).
FROM --platform=linux/amd64 mcr.microsoft.com/dotnet/sdk:10.0

ENV CUE4PARSE_SKIP_NATIVE=true

WORKDIR /src
COPY . /src

# Restore + build once at image-build time.
RUN dotnet build sf-extract.csproj -c Release -p:CUE4PARSE_SKIP_NATIVE=true

# Bake the native decompression libs into the image. CUE4Parse would otherwise try
# to download these at runtime into the cwd and load them by bare name -- but
# dlopen("libz-ng.so") searches the loader path, NOT the cwd, so that fails. We
# fetch valid linux-x64 builds at image-build time and put them on LD_LIBRARY_PATH.
#   - libz-ng.so           : Zlib-ng.NET release (matches ZlibHelper.DOWNLOAD_URL_LINUX)
#   - liboodle-data-shared : WorkingRobot/OodleUE release (matches OodleHelper RELEASE_URL)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl unzip ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://github.com/NotOfficer/Zlib-ng.NET/releases/download/1.0.0/libz-ng.so.gz \
        | gzip -d > /src/libz-ng.so \
    && curl -fsSL -o /tmp/oodle.zip \
        https://github.com/WorkingRobot/OodleUE/releases/download/2026-01-25-1223/gcc-x64-release.zip \
    && unzip -j /tmp/oodle.zip 'lib/liboodle-data-shared.so' -d /src \
    && rm -f /tmp/oodle.zip \
    && chmod +x /src/libz-ng.so /src/liboodle-data-shared.so

ENV LD_LIBRARY_PATH=/src

# Game files mount at /game, output at /out (see extract.sh).
ENTRYPOINT ["dotnet", "/src/bin/Release/net10.0/sf-extract.dll"]
