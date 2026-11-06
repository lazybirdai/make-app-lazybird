# Lazybird for Make

[Lazybird](https://www.lazybird.app) is an AI voice and text to speech app. This Make app turns text into natural MP3 voiceovers and manages voices from your Make scenarios.

## Modules

| Group | Module | What it does |
| --- | --- | --- |
| Speech | Generate speech | Turns text or SSML into an MP3 file with any Lazybird voice. |
| Voices | Search voices | Searches the Lazybird voice library or your own voices by text, language, gender or labels. |
| Voices | Get a voice | Returns the details of one voice. |
| Voices | Create a cloned voice | Creates a private voice from a 10–30 second recording, sent as a file or a URL. |
| Voices | Design a voice | Generates a voice sample from a short description. |
| Voices | Delete a voice | Deletes one of your voices. |
| Account | Get my account | Returns your plan and credit usage. |
| Other | Make an API call | Calls any endpoint of the [Lazybird API](https://www.lazybird.app/text-to-speech-api). |

## Connect Lazybird

1. Sign in to [Lazybird](https://www.lazybird.app) and open **Settings → API** ([direct link](https://www.lazybird.app/studio/settings/api)).
2. Create an API key and copy it.
3. In Make, add a Lazybird module, click **Create a connection** and paste the key into **API key**.

## Example scenario

Watch new rows in a Google Sheet → **Lazybird: Generate speech** with the row's text → upload the MP3 to Google Drive.

## Development

The app is kept in the [Make Apps Editor](https://marketplace.visualstudio.com/items?itemName=Integromat.apps-sdk) local file format. `makecomapp.json` maps the files in this repository to the components of the app on Make.

- `tools/upload.py` uploads the files to the app through the Make API.
- `tools/test_scenario.py run` runs a scenario that uses every module, with each module mapping the outputs of the ones before it.

## License

MIT
