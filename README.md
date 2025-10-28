# Automated arXiv podcast generator

Source code for [Machine Learning in Computational Biology Daily Digest](https://open.spotify.com/show/1rKazxSnk5ON9DxvhXsRdB)


This repository automates a full podcast from episode generation to release: 

1. Fetch relevant daily arxiv papers 
2. Feed to OpenAI for summarizing and TTS.
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
