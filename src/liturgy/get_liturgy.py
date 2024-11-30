import requests
from bs4 import BeautifulSoup
from datetime import datetime


def fetch_liturgy(hour="lauds", query_date="today"):
    if query_date == "today":
        query_date = datetime.now().strftime("%Y%m%d")
    # Universalis URL for today's Liturgy of the Hours
    url = f"https://universalis.com/{query_date}/{hour}.htm"

    try:
        # Fetch the webpage
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Universalis content: {e}")
        return

    # Parse the page content with BeautifulSoup
    soup = BeautifulSoup(response.content, "html.parser")

    try:
        # Extract the main content of Laudes
        classes_to_match = ["p", "v", "vi", "shortrule"]

        # Find all matching elements
        content_sections = soup.find_all(
            lambda tag: tag.name == "th"
            or tag.name == "h4"
            or (tag.get("class") and any(cls in tag.get("class") for cls in classes_to_match))
        )

        # Iterate through sections and print their content
        content = iter(content_sections)
        in_text = False
        prayers = []
        current_prayer = []
        while True:
            section = next(content)
            # print(section.name)
            html_class = section.get("class")
            if not html_class is None:
                if "shortrule" in html_class:
                    print("____")
                    if in_text:
                        prayers.append(current_prayer)
                        current_prayer = []
            text = section.text.strip()
            if text == "INTRODUCTION":
                in_text = True
                continue
            if text == "Today":
                prayers.append(current_prayer)
                break

            if in_text:
                if len(text) > 0 and html_class != "podcastentry":
                    current_prayer.append(text)

    except AttributeError as e:
        print(f"Error parsing the Universalis page structure: {e}")

    return prayers


if __name__ == "__main__":
    prayers = fetch_liturgy()
    print(prayers)
