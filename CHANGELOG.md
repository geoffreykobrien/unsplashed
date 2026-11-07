# Changelog

To release: bump `version` in `custom_components/unsplashed/manifest.json`, add a
section below, and push to `main`. The Release workflow tags it and publishes the
release.

## 0.3.0

### Changed
- **One access key for every feed.** Unsplashed now appears as one **Unsplash** account entry that holds your key, with each feed listed under it. Use **Add feed** to add another feed without entering the key again, and **Change feed** to edit one.
- Changing the key (**Reconfigure** on the account, or the re-authentication prompt) applies to every feed on that account.
- Adding the same key a second time is blocked, with a pointer to **Add feed**.
- The `unsplashed_new_image` event now also includes `feed_id` and `feed`.
- Requires Home Assistant 2025.7 or newer.

### Upgrading
- Existing feeds are moved under an account entry automatically on first start. Entity IDs, history, devices, folders and settings are unchanged.

## 0.2.0

### Added
- **Topic picker.** Setup and Configure load Unsplash's featured topics into a multi-select list. You can still type any topic slug, and existing topic settings carry over.
- **Photographers feed.** Up to 10 Unsplash usernames. Each fetch splits its photos evenly between them and interleaves the results.
- **Color filter.** Limit a feed to one dominant color (black and white, black, white, yellow, orange, red, purple, magenta, green, teal or blue). It uses Unsplash search on a random results page, so the feed keeps changing.
- **Include illustrations** option, off by default. Unsplash has mixed illustrations into photo results since January 2025, and this keeps the feed to photos. The integration asks for extra photos in the same request so filtering doesn't shrink the batch.

### Changed
- Setup now has two screens: the access key first, then **What to fetch**, so the topic list can load.
- Paid Unsplash+ images are always skipped.
- Setup explains which filter combinations Unsplash supports.

## 0.1.0

- Initial release.
