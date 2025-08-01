import json
import argparse
import os

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Transcription Review</title>
    <style>
        body {{ font-family: sans-serif; margin: 2em; }}
        .transcript {{ border: 1px solid #ccc; padding: 1em; border-radius: 5px; }}
        .entity {{ font-weight: bold; padding: 2px 4px; border-radius: 3px; }}
        .PER {{ background-color: #ffadad; }}
        .ORG {{ background-color: #add8e6; }}
        .LOC {{ background-color: #ffd6a5; }}
        .DATE {{ background-color: #fdffb6; }}
        .MONEY {{ background-color: #caffbf; }}
        h1, h2 {{ color: #333; }}
    </style>
</head>
<body>
    <h1>Transcription Review</h1>
    <h2>File: {file_name}</h2>
    
    <h2>Entities</h2>
    <ul>
        {entity_list}
    </ul>

    <h2>Full Transcript</h2>
    <div class="transcript">
        <p>{transcript_html}</p>
    </div>

</body>
</html>
"""

def create_review_interface(json_path, output_html_path):
    """
    Generates an HTML review interface from a processed JSON file.
    """
    print(f"Generating review interface for {json_path}...")

    # If a directory with the same name exists, remove it.
    if os.path.isdir(output_html_path):
        print(f"Warning: Found directory at {output_html_path}. Removing it.")
        try:
            os.rmdir(output_html_path)
        except OSError as e:
            print(f"Error: Could not remove directory {output_html_path}: {e}")
            return

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: The file '{json_path}' was not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from '{json_path}'.")
        return

    full_transcript = data.get("full_transcript", "")
    entities = data.get("entities", [])

    # Create the list of entities for the top section
    entity_list_items = ""
    if entities:
        for entity in entities:
            entity_list_items += f'<li><span class="entity {entity["type"]}">{entity["text"]}</span> ({entity["type"]})</li>'
    else:
        entity_list_items = "<li>No entities found.</li>"

    # Highlight entities in the main transcript
    # This is a simple replacement. A more robust solution would handle overlapping entities.
    transcript_html = full_transcript
    for entity in sorted(entities, key=lambda x: len(x['text']), reverse=True):
        highlighted_entity = f'<span class="entity {entity["type"]}">{entity["text"]}</span>'
        transcript_html = transcript_html.replace(entity["text"], highlighted_entity)
    
    # Replace newlines with <br> for HTML display
    transcript_html = transcript_html.replace("\\n", "<br>")

    # Populate the final HTML
    final_html = HTML_TEMPLATE.format(
        file_name=json_path,
        entity_list=entity_list_items,
        transcript_html=transcript_html
    )

    with open(output_html_path, 'w', encoding='utf-8') as f:
        f.write(final_html)
    
    print(f"Review interface saved to {output_html_path}")

def main():
    parser = argparse.ArgumentParser(description="Generate an HTML review interface.")
    parser.add_argument("json_path", help="Path to the processed JSON transcription file.")
    parser.add_argument("output_html_path", help="Path to save the output HTML file.")
    args = parser.parse_args()
    create_review_interface(args.json_path, args.output_html_path)

if __name__ == "__main__":
    main()