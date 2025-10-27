import os
import sys
import argparse
import re
from datetime import datetime
from pathlib import Path
import tempfile

import pandas as pd

from liturgy.get_liturgy import fetch_liturgy
from liturgy.arxiv import get_papers 
from liturgy.summarize import make_summary
from liturgy.tts import get_audio
from liturgy.build_track import build_track

chunk_size = 2


def cline():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Date in YYYY-MM-DD format, or 'today'", default="today")
    parser.add_argument("--debug", help="Compile short snippet", default=False, action="store_true")
    return parser.parse_args()


def split_summary(summary):
    text = "".join(summary)
    sentences = re.split(r"(?<=[.!?]) +", text)
    return sentences

def get_summaries(date, topic="q-bio.BM", summaries_subdir="summaries"):
    """
    Return a list of summary strings for all PDFs in `outdir`.

    If a summary file already exists in `<outdir>/<summaries_subdir>/<pdfname>.txt`,
    read and append it. Otherwise, call `make_summary(pdf_path)`, append the result,
    and save it to that folder for future runs.
    """

    outdir = Path(f"database/{date}")

    print("Fetching papers")
    lists = ["cs.LG", "cs.AI", "q-bio.BM", "cs.CL", "q-bio.QM"]
    keywords = ["protein", 
                "dna", 
                "rna", 
                "cryo-EM"]
    get_papers(date=date, 
               cats=lists,
               keywords=keywords,
               out=str(outdir)
               )

    print("Summarizing ...")
    # Choose/create summaries directory: prefer <outdir>/summaries; fall back to ./summaries if it already exists.
    summaries_dir = outdir / summaries_subdir
    if not summaries_dir.exists():
        alt = Path(summaries_subdir)
        summaries_dir = alt if alt.exists() else summaries_dir
    summaries_dir.mkdir(parents=True, exist_ok=True)

    pdf_paths = sorted(outdir.glob("*.pdf"))
    if not pdf_paths:
        print(f"No PDFs found in {outdir}", file=sys.stderr)
        return []

    results = []
    for p in pdf_paths:
        summary_file = summaries_dir / (p.stem + ".txt")
        print(summary_file)

        # If we already summarized this PDF, reuse it.
        if summary_file.exists():
            try:
                results.append(summary_file.read_text(encoding="utf-8"))
                print("Loading existing summary.")
                continue
            except Exception as e:
                print(f"Failed to read existing summary for {p.name}: {e} (will regenerate)", file=sys.stderr)

        # Otherwise, generate and save a new summary.
        try:
            print(f"Generating summary for {p}...")
            # summary = make_summary(str(p))
            summary = ""
            try:
                summary_file.write_text(summary, encoding="utf-8")
                results.append(summary_file.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"Failed to write summary for {p.name}: {e}", file=sys.stderr)
        except Exception as e:
            print(f"Failed to summarize {p.name}: {e}", file=sys.stderr)

    return results


def build_episode(args):

    if args.date == "today":
        query_date = datetime.now().strftime("%Y-%m-%d")
    else:
        query_date = args.date

    Path("texts").mkdir(parents=True, exist_ok=True)

    if args.debug:
        summaries = [
            [
                "Our Father who art in heaven.",
                "Hallowed be thy name.",
                "Thy kingdom come, thy will be done.",
                "On earth as it is in heaven.",
                "On earth as it is in heaven.",
                "Give us this day our daily bread.",
                "And forgive us our trespasses, as we forgive those who trespass against us."
                "And lead us not into temptation; but deliver us from evil.",
                "Amen.",
            ]
        ]
    else:
        summaries = get_summaries(date=query_date)
    all_text = ""
    fg_paths = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for i, summary in enumerate(summaries):
            summary_paths = []
            summary = split_summary(summary)
            for i in range(0, len(summary), chunk_size):
                text = " ".join(summary[i : i + chunk_size])
                all_text += text + "\n"
                print("Making audio for {i+1} of {len(summaries)}")
                print(text)
                audio_path = get_audio(text, recompute=True, save_dir=tmpdir)
                summary_paths.append(audio_path)
            all_text += "\n" + "_" * 12 + "\n\n"
            fg_paths.append(summary_paths)
        print("Building track")
        if args.debug:
            build_track(fg_paths, f"debug.mp3", overwrite=True)
        else:
            build_track(fg_paths, f"episodes/{query_date}.mp3", overwrite=True)

    with open(f"texts/{query_date}.txt", "w") as txt:
        metadata_csv = pd.read_csv(f"database/{query_date}/metadata.csv")
        text = []
        for row in metadata_csv.itertuples():
            text.append(f"{row.title} {row.pdf_url}")
        txt.write("\n".join(text))


if __name__ == "__main__":
    build_episode(cline())
