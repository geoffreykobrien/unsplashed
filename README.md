# Unsplashed

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![Validate](https://github.com/geoffreykobrien/unsplashed/actions/workflows/validate.yml/badge.svg)](https://github.com/geoffreykobrien/unsplashed/actions/workflows/validate.yml)
![Home Assistant 2025.7+](https://img.shields.io/badge/Home%20Assistant-2025.7%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A Home Assistant integration that saves fresh photos from [Unsplash](https://unsplash.com) to a local folder on a schedule. Each photo is cropped to the exact size of your screen.

I built it to feed a portrait kitchen wall display. Point a slideshow at the folder (for example [Album Slideshow](https://github.com/eyalgal/album_slideshow) using its **Local folder** provider) and the display gets new photos every day without anyone touching it.

---

## Features

- **Set up entirely in the UI.** You enter your Unsplash access key once, then add as many feeds as you like with **Add feed**. No YAML, no `secrets.yaml`, no shell commands.
- **Photos sized to your screen.** Set a width and height and every photo comes back cropped to exactly that size. Unsplash only returns photos in the matching orientation, so a 1080×1920 screen gets portrait photos.
- **Choose what you get.** Filter by search words (`maine, coast, autumn`), Unsplash topics (picked from Unsplash's live list), public collection IDs, or specific photographers.
- **Match a color.** Limit a feed to photos dominated by one color, such as blue, orange or black and white, to suit a room or season.
- **Photos only.** Unsplash now mixes illustrations into its photo results. They're filtered out unless you turn them on. Paid Unsplash+ images are always skipped.
- **Runs on a schedule.** Fetches every *N* hours. A Home Assistant restart doesn't trigger an extra fetch, because the last fetch time is saved.
- **Cleans up after itself.** Deletes its own photos once they're older than a set number of days. It only touches files named `unsplash_*.jpg`, so other photos in the same folder are never removed.
- **Safe for slideshows.** Files are written to a temporary name and renamed when complete, so a slideshow never loads a half-downloaded image.
- **Entities and an event for automations.** Includes a **Fetch now** button, a **Latest photo** image entity, sensors for the photo count, photographer credit and last fetch, and an `unsplashed_new_image` event.
- **Follows Unsplash's rules.** Reports every download to Unsplash as its API guidelines require, and exposes the photographer credit for each photo.
- **Recovers from a bad key.** If Unsplash ever rejects your key, Home Assistant asks you for a new one instead of failing silently.

---

## Installation

### Marketplace (Home Assistant 2026.11+) or HACS (recommended)

1. On Home Assistant 2026.11 or later, go to **Settings → Marketplace → Add from link**. On older versions, open **HACS**, then the **⋮** menu → **Custom repositories**.
2. Enter `https://github.com/geoffreykobrien/unsplashed` as an **Integration**.
3. Install **Unsplashed**, then restart Home Assistant.

### Manual

1. Download the latest release.
2. Copy `custom_components/unsplashed` into your Home Assistant `config/custom_components/` folder.
3. Restart Home Assistant.

---

## Get an Unsplash access key

The key is free and takes about two minutes to get.

1. Sign in at [unsplash.com](https://unsplash.com) (create an account if you need one).
2. Go to [unsplash.com/oauth/applications](https://unsplash.com/oauth/applications) and click **New Application**.
3. Accept the API terms, give the app a name (for example *Home Assistant wallpapers*), and create it.
4. On the app page, scroll to **Keys** and copy the **Access Key**. You don't need the Secret Key.

New apps start in **demo mode**, which allows **50 API requests per hour**. That's far more than this integration needs (see [Rate limits](#rate-limits)).

---

## Setup

1. Go to **Settings → Devices & services → Add integration** and choose **Unsplashed**.
2. Paste your **Access key**. Setup checks it with Unsplash and loads the current list of featured topics.
3. On the **Your first feed** screen, fill in the options below and click **Submit**. The first batch of photos downloads right away.

The integration then appears as one **Unsplash** account holding your key, with your feed listed under it.

### Adding more feeds

Open **Settings → Devices & services → Unsplashed** and click **Add feed**. You won't be asked for the key again. Each feed has its own filters, size, schedule and folder, for example a portrait feed for the kitchen and a landscape feed for the TV. All feeds share the key's hourly request limit, so add up their requests (see [Rate limits](#rate-limits)).

To change a feed, click **⋮** next to it and choose **Change feed**. To remove one, choose **Delete**. Its saved photos stay on disk.

To change the access key all your feeds use, click **⋮** next to the **Unsplash** account and choose **Reconfigure**. If Unsplash ever rejects the key, Home Assistant prompts you for a new one, which also applies to every feed. To use two different Unsplash keys, add the integration a second time with the other key.

### Upgrading from 0.2.x or earlier

Before 0.3.0, every feed was its own setup with its own copy of the key. On the first start after upgrading, each existing feed is moved under an **Unsplash** account entry automatically. Its entities, entity IDs, history, folder and settings stay exactly as they were, so dashboards and automations keep working. If you had several feeds with the same key, each becomes its own account entry. You can leave them like that, or recreate them with **Add feed** under one account.

### Feed options

| Option | Default | What it does |
| --- | --- | --- |
| **Search words** | *(empty)* | Comma-separated keywords, such as `maine, coast, autumn forest`. |
| **Topics** | *(empty)* | Pick one or more of Unsplash's featured [topics](https://unsplash.com/t) from the list, or type any topic slug. |
| **Collections** | *(empty)* | Comma-separated public collection IDs. |
| **Photographers** | *(empty)* | Up to 10 comma-separated Unsplash usernames, such as `chrislawton, @nasa`. Each fetch splits its photos between them. |
| **Color** | Any color | Only photos dominated by this color: black and white, black, white, yellow, orange, red, purple, magenta, green, teal or blue. |
| **Photos per fetch** | `3` | How many photos each fetch downloads (1–30). |
| **Fetch every** | `24` h | Hours between fetches (1–168). |
| **Width / Height** | `1080` × `1920` | Exact output size in pixels. The orientation filter follows from these values. |
| **Save to folder** | `/media/wallpapers` | Absolute path. Created automatically if it doesn't exist. |
| **Delete photos older than** | `30` days | Set to `0` to keep everything forever. |
| **Strict content filter** | off | Asks Unsplash for its stricter, family-friendly filtering. |
| **Include illustrations** | off | Unsplash has mixed illustrations into photo results since January 2025. Leave this off to keep the feed to photos. |

Unsplash only supports some filter combinations, and setup tells you if you pick one it doesn't support:

| Combination | Allowed? |
| --- | --- |
| Search words + topics or collections | No, use one or the other |
| Photographers + anything else | No, photographers stand alone |
| Color + search words and/or collections | Yes |
| Color + topics | No, Unsplash's color filter only works with search |
| Color with no search words | Yes, the color's name is used as the search (for example `blue`) |

If you leave every filter empty, you get random photos from all of Unsplash.

---

## Entities

Each feed gets its own device, named after the feed (for example **Unsplashed: maine, coast**), with these entities.

| Entity | Description |
| --- | --- |
| `button.*_fetch_now` | Downloads a new batch right away, outside the schedule. |
| `image.*_latest_photo` | The most recently saved photo. |
| `sensor.*_latest_photo_credit` | For example *"Photo by Jane Doe on Unsplash"*. Attributes include `description`, `photographer`, `photographer_url`, `photo_url`, `location`, `color` and `path`. |
| `sensor.*_photos_in_folder` | How many of this integration's photos are currently in the folder. |
| `sensor.*_last_fetch` | When the last fetch ran. The `new_images` attribute shows how many photos it saved. |
| `sensor.*_api_requests_remaining` | Requests left this hour, as reported by Unsplash. Diagnostic, and disabled by default. |

### Event: `unsplashed_new_image`

Fired once for each photo saved. The event data includes `entry_id`, `feed_id`, `feed` (the feed's name), `id`, `path`, `description`, `photographer`, `photographer_url`, `photo_url`, `location`, `color`, `credit` and `saved_at`.

---

## Using it with a slideshow

### Album Slideshow (local folder)

1. Set up Unsplashed with the folder set to `/media/wallpapers`.
2. Add an **Album Slideshow** integration entry, choose **Local folder**, and enter `/media/wallpapers`.
3. Use that entry's camera in an `album-slideshow-card`:

```yaml
type: custom:album-slideshow-card
entity: camera.album_slideshow_wallpapers
transition: fade
fit: cover
```

Album Slideshow re-reads the folder on its own refresh schedule (the **Album refresh** number entity), so new photos appear automatically.

To mix Unsplash photos with your own, set Unsplashed to save into the same folder your family photos are in. It only ever creates or deletes `unsplash_*.jpg` files there.

### A plain picture card

The **Latest photo** image entity works anywhere an image entity does:

```yaml
type: picture-entity
entity: image.unsplashed_maine_coast_latest_photo
show_name: false
show_state: false
```

---

## Automation examples

**Show a new photo on the display as soon as it arrives:**

```yaml
alias: Advance kitchen slideshow when Unsplash photos arrive
triggers:
  - trigger: event
    event_type: unsplashed_new_image
actions:
  - action: button.press
    target:
      entity_id: button.album_slideshow_wallpapers_refresh_album
mode: single
```

**Fetch a fresh batch every morning at 5 AM instead of on a fixed interval:**

Set **Fetch every** to `168` h so the built-in schedule rarely fires, then:

```yaml
alias: Morning Unsplash fetch
triggers:
  - trigger: time
    at: "05:00:00"
actions:
  - action: button.press
    target:
      entity_id: button.unsplashed_maine_coast_fetch_now
```

---

## Rate limits

Unsplash counts requests to `api.unsplash.com`. The image downloads themselves come from Unsplash's CDN and don't count.

Each fetch uses **1 request** to choose photos (or **1 per photographer** in a photographers feed), plus **1 request per photo** to report the download as Unsplash requires. Filtering out illustrations doesn't cost extra requests: the integration just asks for a few more photos in the same request. That works out to:

| Photos per fetch | Requests per fetch |
| --- | --- |
| 3 | 4 |
| 10 | 11 |
| 30 (max) | 31 |

Even at the maximum settings (30 photos, hourly) a single feed stays under the demo limit of 50 requests per hour. If you run several feeds on one key with a short interval, add up their totals. Setup checks the key and loads the topic list with two extra requests, and **Add feed** or **Change feed** loads the topic list again (one request).

If Unsplash returns a rate-limit error, the fetch is skipped and retried at the next interval. Nothing breaks.

---

## Unsplash guidelines and attribution

Photos on Unsplash are free to use under the [Unsplash License](https://unsplash.com/license). The API has its own [guidelines](https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines). This integration:

- **Reports every download** to Unsplash's `download_location` endpoint, so photographers get credit for each use.
- **Exposes attribution** through the **Latest photo credit** sensor and the `unsplashed_new_image` event, so you can show *"Photo by … on Unsplash"* on your dashboard.
- **Keeps Unsplash's tracking parameter** (`ixid`) in every image URL it requests.

The API guidelines prefer apps to hotlink images from Unsplash's CDN rather than store copies. This integration saves local copies so that slideshow integrations that only read folders can use them. It's meant for personal, non-commercial home displays. If you publish or redistribute the photos, follow Unsplash's guidelines directly.

---

## Troubleshooting

**"Unsplash rejected that access key."** Make sure you copied the **Access Key**, not the Secret Key, and that the app wasn't deleted at unsplash.com/oauth/applications.

**"Home Assistant can't create or write to that folder."** Use a path Home Assistant can write to. On Home Assistant OS, anything under `/media` or `/config/www` works. Paths on a network share need the share mounted first under **Settings → System → Storage**.

**No photos arrive.** Check **Settings → System → Logs** for `unsplashed` entries. A very narrow search (an unusual word combined with portrait orientation, or a rare color) can return no results. Try broader search words or a topic like `nature`. In a photographers feed, a photographer with few photos in your orientation may have none to give; the log names them.

**A drawing showed up anyway.** Unsplash marks illustrations with an asset type, and the filter relies on that. If one slips through unmarked, open an issue with the photo's link.

**Debug logging.** Add this to `configuration.yaml` and restart:

```yaml
logger:
  logs:
    custom_components.unsplashed: debug
```

---

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install pytest-homeassistant-custom-component
pytest -q
```

GitHub Actions runs HACS validation, `hassfest`, and the test suite on every push.

### Releases

When `version` in `manifest.json` changes on `main`, the **Release** workflow tags it (`vX.Y.Z`) and publishes a GitHub release using the matching section of [CHANGELOG.md](CHANGELOG.md), so HACS and the Home Assistant Marketplace offer it as an update.

---

## License

MIT. See [LICENSE](LICENSE).

This project isn't affiliated with or endorsed by Unsplash. Photos belong to their photographers and are used under the [Unsplash License](https://unsplash.com/license).
