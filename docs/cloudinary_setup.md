# Cloudinary Setup

## Required Environment Variables

Cloudinary storage is controlled entirely by environment variables:

```text
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret
USE_CLOUDINARY_STORAGE=True
```

Set `USE_CLOUDINARY_STORAGE=False` or omit it to use local `MEDIA_ROOT` storage and the existing hackathon media-serving fallback.

## Local Development

For local development with filesystem uploads:

```text
USE_CLOUDINARY_STORAGE=False
DEBUG=True
```

Local uploads continue to use:

```text
MEDIA_URL=/media/
MEDIA_ROOT=<project>/media
```

For local Cloudinary testing, add the Cloudinary credentials to `.env` and set:

```text
USE_CLOUDINARY_STORAGE=True
```

New medicine uploads will then use Cloudinary storage automatically. No model or template changes are needed because `Medicine.medicine_image` uses Django's configured default storage.

## Render Deployment

Add these environment variables in the Render dashboard:

```text
CLOUDINARY_CLOUD_NAME
CLOUDINARY_API_KEY
CLOUDINARY_API_SECRET
USE_CLOUDINARY_STORAGE=True
```

Keep `DEBUG=False` in Render. With Cloudinary enabled, uploaded medicine images are served from Cloudinary hosted URLs. If Cloudinary is disabled, the existing temporary hackathon `/media/...` fallback can still serve files from `MEDIA_ROOT`.

## Switching Storage

Use Cloudinary:

```text
USE_CLOUDINARY_STORAGE=True
```

Use local filesystem fallback:

```text
USE_CLOUDINARY_STORAGE=False
```

Existing local media files remain usable when local storage is selected. Cloudinary-hosted images render through their Cloudinary URLs when Cloudinary storage is selected.

## Why Cloudinary For Hackathon Demos

Cloudinary is recommended for hackathon demos because uploaded medicine images survive redeploys, work across Render instances, and do not depend on a local filesystem. It keeps the current Django SSR upload flow intact while avoiding a heavier storage buildout.
