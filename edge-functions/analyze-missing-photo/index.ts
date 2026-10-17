// analyze-missing-photo
//
// Suggests title, description, category and color for a student's missing-item report from a
// photo of the item, using Perceptron Mk1.5. The app pre-fills its report form with the result
// before inserting into `missing_reports`, so matching runs on the app's exact category
// spellings. Matching only runs on INSERT, which is why this suggests rather than updates.
//
// Auth: a signed-in user's Supabase JWT (verify_jwt = true); the anon key alone is rejected.
// Storage reads run as the caller, so a student can only analyze their own `missing-photos`.
//
// Body (exactly one of):
//   image_path    string   object path in the private `missing-photos` bucket
//   image_base64  string   raw base64 or a data: URL, for analyzing before upload
//
// Response: { item_visible, title, description, category, color }
// When item_visible is false the other fields are best-effort and the app should not pre-fill.

import { createClient } from "npm:@supabase/supabase-js@2";
import { HttpError, json, serve } from "../_shared/http.ts";
import { fromBase64, fromStorage } from "../_shared/images.ts";
import { CATEGORIES, CATEGORY_GUIDE, COLORS } from "../_shared/items.ts";
import { askJson, image, text, toDataUrl } from "../_shared/perceptron.ts";

type Suggestion = {
  item_visible: boolean;
  title: string;
  description: string;
  category: string;
  color: string;
};

const SUGGESTION_SCHEMA = {
  type: "object",
  properties: {
    item_visible: {
      type: "boolean",
      description:
        "False if no single belonging is clearly the subject, e.g. a scene, a person, or clothing being worn.",
    },
    title: {
      type: "string",
      description: "Short report title, e.g. 'Blue Hydro Flask water bottle'. At most 60 characters.",
    },
    description: {
      type: "string",
      description: "One to three sentences: type, brand, material, and distinguishing marks.",
    },
    category: { type: "string", enum: CATEGORIES },
    color: { type: "string", enum: COLORS, description: "The single dominant color." },
  },
  required: ["item_visible", "title", "description", "category", "color"],
  additionalProperties: false,
};

const PROMPT = `A student lost this item and is filing a lost-and-found report with this photo.
Describe the main item so the report can be matched against items found on campus.

Use only what you can clearly see, and leave out anything you are unsure of. Prefer details that
tell this item apart from identical products, such as stickers, scratches, wear, cases, keychains
or engravings, but only when they are actually visible. Never transcribe names, ID numbers or
other personal text: the report is matched against public listings.

${CATEGORY_GUIDE}`;

const str = (v: unknown) => (typeof v === "string" && v.trim() ? v.trim() : undefined);

serve(async (body, req) => {
  const imagePath = str(body.image_path), imageBase64 = str(body.image_base64);
  if (!imagePath === !imageBase64) throw new HttpError(400, "Send exactly one of image_path, image_base64");

  const authorization = req.headers.get("Authorization");
  if (!authorization) throw new HttpError(401, "Missing Authorization header");
  // Acts as the caller, so Storage policies limit this to the student's own photos.
  const supabase = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_ANON_KEY")!, {
    global: { headers: { Authorization: authorization } },
    auth: { persistSession: false },
  });
  // The gateway also accepts the public anon key; require a signed-in user so the key bundled
  // in the app can't be used to spend Perceptron credits.
  const { data: { user } } = await supabase.auth.getUser(authorization.replace(/^Bearer\s+/i, ""));
  if (!user) throw new HttpError(401, "Sign in to analyze photos");

  const photo = imagePath ? await fromStorage(supabase, "missing-photos", imagePath) : fromBase64(imageBase64!);

  const s = await askJson<Suggestion>(
    [image(toDataUrl(photo.bytes, photo.mime)), text(PROMPT)],
    "missing_item",
    SUGGESTION_SCHEMA,
    512,
  );
  return json({
    ...s,
    // missing_reports.title must be 1-150 characters.
    title: s.title.trim().slice(0, 150) || "Lost item",
    category: CATEGORIES.includes(s.category) ? s.category : "Other",
  });
});
