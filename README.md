# Automated Daily Prayer Podcast

Source code for [Liturgy of the Hours podcast](https://open.spotify.com/show/1LHNP0yiopuiHFRjAguaXg?si=9075cdf6007642cd).

This repository automates a full podcast from episode generation to release: 

1. Fetch daily prayers
2. Feed to TTS engine for reading.
3. Set to background music.
4. Upload to DigitalOcean Spaces
5. Update XML feed.


You can use this to generate your own podcast by tweaking a few variables to make sure they match your setup (e.g. API keys).

## Install

```
pip install -r requirements.txt
```

## Release Today's Prayers

```
chmod u+x release.sh
./release.sh
```
