Place the verified Windows x64 ffmpeg.exe and ffprobe.exe in this directory
before running scripts/build_release.py.

The local v1.4.5 release build uses the Gyan.FFmpeg 8.1.2 full build documented
under tools/licenses/ffmpeg/. The executables are intentionally ignored by Git
because each file exceeds GitHub's normal per-file limit. They are embedded in
the generated Windows ZIP and verified with the -version command.
