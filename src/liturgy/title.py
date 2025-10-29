from __future__ import annotations
from typing import List
from openai import OpenAI


def generate_episode_title(paper_titles: List[str], *, model: str = "gpt-4.1", max_words: int = 12) -> str:
    """
    Given a list of paper titles, ask the OpenAI API to craft ONE concise,
    descriptive podcast episode title that reflects the combined themes.
    Returns just the title string.

    Example:
        titles = [
            "Protein generation with embedding learning for sequence design",
            "SO(3)-invariant PCA with application to molecular structures",
            "Speak to a Protein: An Interactive Multimodal Interface"
        ]
        print(generate_episode_title(titles))
    """
    client = OpenAI()
    if not paper_titles:
        raise ValueError("paper_titles must not be empty")

    list_block = "\n".join(f"- {t}" for t in paper_titles)

    prompt = (
        "Generate a comma separated list of maximum three descriptive words"
        "for three of the most interesting papers, end it with 'and more'"
        "Use Title Case. Return only the title text on a single line.\n\n"
        f"Paper titles:\n{list_block}"
    )

    resp = client.responses.create(
        model=model,
        temperature=0.7,
        input=[{
            "role": "user",
            "content": [{"type": "input_text", "text": prompt}],
        }],
    )

    title = (resp.output_text or "").strip().splitlines()[0] if resp else ""
    # light cleanup: strip surrounding quotes and a trailing period
    return title.strip(" \"'“”‘’").rstrip(".")
