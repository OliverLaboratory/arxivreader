# Automated Daily Prayer Reading Podcast

Source code for [Liturgy of the Hours podcast](https://open.spotify.com/show/1LHNP0yiopuiHFRjAguaXg?si=9075cdf6007642cd).

<div align="center">
<a href="https://open.spotify.com/show/1LHNP0yiopuiHFRjAguaXg?si=9075cdf6007642cd"><img src="images/cover.png" width="300"></a>
</div>


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

## Build Today's Episode

```
python src/build_episode.py
```

Will create an entry in `episodes/` with the episode mp3.


## Update XML feed


```
python src/liturgy/feed.py
```

Creates XML file with all episodes in `episodes/`

## Automated releases

```
chmod u+x release.sh
./release.sh
```

---

Support development and hosting costs with [donation](https://ko-fi.com/liturgy).
