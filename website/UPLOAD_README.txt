VirtualGlove public website
===========================

Source files live in website/src. Do not edit website/dist or the upload ZIP
by hand.

Build from the repository root:

    python3 website/build.py

The build reads config/release.json, recreates website/dist, and writes:

    output/website/VirtualGlove-Website.zip

For manual publishing, upload the contents of website/dist or extract and
upload the ZIP. Both contain the same verified files.

To promote a release candidate, update config/release.json and rebuild. The
version labels, tag-specific links, download links, and install commands are
generated from those central release facts.
