
# Prompt Maker

A terminal app (built with [Textual](https://github.com/Textualize/textual)) for browsing AI prompt templates, filling in their variables through a form, and saving the result as Markdown or JSON.

*This project was written with the aid of AI.*

## Features

-   **Browse templates** — pick a prompt template from a list and open it in a side-by-side fill-in form with a live preview of the template file.
-   **Fill-in forms** — templates declare typed variables (single-line or multiline) with optional defaults; the app builds the form for you.
-   **Save as `.md` or `.json`** — choose the output format per run, or set a default with `/output`.
-   **Reuse the last run** — `/reuse` reopens the last template with the same values already filled in.
-   **Template management** — create, edit, and delete templates from inside the app (`/newtemplate`, `/organize`), backed by a raw JSON editor.
-   **Custom color themes** — create, edit, and switch between themes (`/newtheme`, `/theme`, `/themesorganize`), with a live color preview and click-to-copy hex values.
-   **Command bar** — type `/` for a suggested command list (`/help` shows them all).

## Installation

```bash
git clone https://github.com/Ailer-h/prompt-maker.git
cd prompt-maker
pip install -r requirements.txt

```

Requires Python and [Textual](https://textual.textualize.io/) `>=8.2.8`.

## Usage

```bash
python app.py
```

| Flag | Description |
| --- | --- |
| `--templates PATH` | Use a directory of `.json` templates instead of the default `templates/` folder. |
| `--output-dir PATH` | Directory new prompt files are written to (defaults to the current working directory). |

### Controls

-   **Up / Down arrows** — browse templates
-   **Enter** — open the selected template
-   **/** — focus the command bar

### Commands

| Command | Description |
| --- | --- |
| `/output` | Choose the file extension (`.md` or `.json`) new prompts are saved with. |
| `/reuse` | Reopen the last template with the same field values. |
| `/newtemplate` | Create a new prompt template. |
| `/organize` | Browse, edit, or delete templates. |
| `/theme` | Choose the active color theme. |
| `/newtheme` | Create a new color theme. |
| `/themesorganize` | Browse, edit, or delete custom themes. |
| `/reloadthemes` | Reload theme files from disk (e.g. after editing one externally). |
| `/help` | List the available commands. |


## Templates

Templates live in the `templates/` folder as JSON files:

```json
{
  "name": "New Template",
  "description": "",
  "template": "{{steps}}",
  "variables": [
    {
      "name": "example_var",
      "label": "Example variable",
      "multiline": false,
      "default": ""
    }
  ],
  "steps": []
}
```

-   `template` (required) — the text of the prompt, with `{{variable_name}}` placeholders.
-   `variables` — the fields shown in the fill-in form.
-   `steps` — optional structured steps, included when saving to `.json`.

## Themes

Themes live in the `themes/` folder as JSON files:

```json
{
  "name": "new-theme",
  "dark": true,
  "primary": "#2e3440",
  "secondary": "",
  "accent": "",
  "background": "",
  "surface": "",
  "panel": "",
  "foreground": "",
  "warning": "",
  "error": "",
  "success": ""
}
```

-   `primary` is the only required color; everything else falls back to Textual's default for that slot when left blank.
-   `dark` marks whether the theme has a dark background (affects contrast).

## Project structure

```
prompt-maker/
├── app.py             # App entry point, screens, and top-level logic
├── config.py          # Load/save user preferences (output format, theme)
├── templates.py       # Template model and loading
├── theme_changer.py   # Theme model and loading
├── requirements.txt
├── widgets/           # Custom widgets (e.g. the template fill-in form)
├── templates/         # Bundled prompt templates
└── themes/            # Bundled color themes
```
