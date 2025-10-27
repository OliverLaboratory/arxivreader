from openai import OpenAI

def make_summary(pdf_path):
    client = OpenAI()

    pdf = client.files.create(file=open(pdf_path, "rb"), purpose="user_data")

    prompt = """summarize this pdf for a person who knows the field in about
    700 words. don't give me any formatting or headers. just the text written
    as paragraphs, no bullet points. write as though it were a monologue being spoken
    by a person, at the start state the title and the authors. no special
    characters."""

    resp = client.responses.create(
        model="gpt-4.1",
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text",\
                 "text": prompt},
                {"type": "input_file", "file_id": pdf.id}
            ]
        }]
    )

    return resp.output_text
