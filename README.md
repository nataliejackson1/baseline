# Sugar Buddy

## Required setup

1. Create a Supabase project and run [supabase/schema.sql](supabase/schema.sql) in the SQL editor.
2. Deploy [supabase/functions/recommend-meal/index.ts](supabase/functions/recommend-meal/index.ts) as the `recommend-meal` Edge Function.
3. Add `GROQ_API_KEY` to the Edge Function secrets. `GROQ_MODEL` is optional.
4. Enable Dexcom Share and add these GitHub Actions secrets:

	- `DEXCOM_SHARE_USERNAME`
	- `DEXCOM_SHARE_PASSWORD`
	- `DEXCOM_REGION` (`us`, `ous` for outside the US, or `jp` for Japan)
	- `SUPABASE_URL`
	- `SUPABASE_SERVICE_KEY`
	- `ONESIGNAL_APP_ID`
	- `ONESIGNAL_API_KEY`
	- `GROQ_API_KEY`
	- `GROQ_MODEL` (optional)

5. Create a OneSignal Web Push app and use its App ID and REST API key above.
6. In [glucose-meal-coach.html](glucose-meal-coach.html), set:

	- `SUPABASE_URL`
	- `SUPABASE_ANON_KEY`
	- `ONESIGNAL_APP_ID`

7. Host `glucose-meal-coach.html` over HTTPS, such as with GitHub Pages, Netlify, or Vercel.

The GitHub Actions workflow runs the Dexcom Share ingestion every ten minutes. The browser uses only the Supabase anon key. Never expose `SUPABASE_SERVICE_KEY`, Dexcom credentials, OneSignal REST credentials, or `GROQ_API_KEY` in the HTML.
