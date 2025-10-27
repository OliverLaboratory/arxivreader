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
from liturgy.build_track import build_track

chunk_size = 2

with open("OPENAI.txt", "r") as oai:
    key = oai.readline().strip()

os.environ["OPENAI_API_KEY"] = key

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
                "cryo-EM",
                "Protein-Protein",
                "Protein-Nucleic",
                "Protein-Small",
                "RNA-small",
                "Molecule",
                "Molecular",
                "atomic",
                "atom"]
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

    summary_audio_paths = []
    for p in pdf_paths:
        summary_file = summaries_dir / (p.stem + ".mp3")

        # If we already summarized this PDF, reuse it.
        if summary_file.exists():
            try:
                summary_audio_paths.append(summary_file)
                print("Loading existing summary.")
                continue
            except Exception as e:
                print(f"Failed to read existing summary for {p.name}: {e} (will regenerate)", file=sys.stderr)

        # Otherwise, generate and save a new summary.
        try:
            print(f"Generating summary for {p}...")
            summary_path, summary_text = make_summary(str(p), summary_file)
            summary_audio_paths.append(summary_path)
        except Exception as e:
            print(f"Failed to summarize {p.name}: {e}", file=sys.stderr)

    return summary_audio_paths 


def build_episode(args):

    if args.date == "today":
        query_date = datetime.now().strftime("%Y-%m-%d")
    else:
        query_date = args.date

    Path("texts").mkdir(parents=True, exist_ok=True)

    audio_paths = get_summaries(date=query_date)
    print(audio_paths)
    audio_path, timestamps = build_track(audio_paths, f"episodes/{query_date}.mp3", overwrite=True)

    with open(f"texts/{query_date}.txt", "w") as txt:
        metadata = pd.read_csv(f"database/{query_date}/metadata.csv", dtype={"arxiv_id":"string"})
        print(metadata)
        text = ["This podcast is brought to you by the Oliver Laboratory"\
                " at Vanderbilt University.",\
                "-"*40]
        for audio_path, time in zip(audio_paths, timestamps):
            audio_id = str(Path(audio_path).stem.split("-")[1])
            print(audio_id)
            paper_data = metadata.loc[metadata['arxiv_id'] ==
                                      str(audio_id)].reset_index()
            print(paper_data)
            text.append(f"{time} {paper_data['title'].iloc[0]}"\
                        f" ({paper_data['pdf_url'].iloc[0]})")
        text.append("-"*40)
        text.append("Source code: "\
                    "https://github.com/OliverLaboratory/arxivreader")
        text.append("Contact: "\
                    "oliverlaboratory.com")
        txt.write("\n".join(text))


if __name__ == "__main__":
    build_episode(cline())
