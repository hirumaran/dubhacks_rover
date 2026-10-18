// Prompts, schema and Perceptron calls for judging whether two photos show the same object:
// a missing report vs a found listing, or a new rover sighting vs an existing listing.
// Kept free of Supabase so it can be exercised directly.

import type { LoadedImage } from "./images.ts";
import { askJson, type ContentPart, image, text, toDataUrl } from "./perceptron.ts";

export type Report = {
  id: string;
  title: string;
  description: string;
  category: string;
  color: string;
  image_path: string | null;
};
export type Found = Omit<Report, "image_path"> & { image_path: string };

export type Rating = {
  similarity: number;
  verdict: "same_item" | "likely_same" | "unsure" | "likely_different" | "different";
  matching_features: string[];
  differences: string[];
  summary: string;
};

const RATING_SCHEMA = {
  type: "object",
  properties: {
    similarity: {
      type: "integer",
      minimum: 0,
      maximum: 100,
      description: "How likely it is that both refer to the same physical object, 0-100.",
    },
    verdict: { type: "string", enum: ["same_item", "likely_same", "unsure", "likely_different", "different"] },
    matching_features: { type: "array", items: { type: "string" }, description: "Visible details that agree." },
    differences: { type: "array", items: { type: "string" }, description: "Visible details that conflict." },
    summary: { type: "string", description: "One sentence a student can read." },
  },
  required: ["similarity", "verdict", "matching_features", "differences", "summary"],
  additionalProperties: false,
};

// The verdict is the model's most stable output; with long prompts the 0-100 score sometimes
// comes back as 0 even for "same_item". Keep the score inside the range its verdict implies.
const VERDICT_RANGE: Record<Rating["verdict"], [number, number]> = {
  same_item: [85, 100],
  likely_same: [65, 84],
  unsure: [35, 64],
  likely_different: [15, 34],
  different: [0, 14],
};

function consistent(r: Rating): Rating {
  const [lo, hi] = VERDICT_RANGE[r.verdict] ?? [0, 100];
  return { ...r, similarity: Math.max(lo, Math.min(hi, Math.round(r.similarity))) };
}

const RULES = `Judge whether these are the SAME physical object, not just the same kind of product.
Many students own identical mass-produced items, so a matching model and color alone is only
moderate evidence. Unique marks (stickers, scratches, wear, attached keychains, engravings, cases)
are strong evidence either way. Either photo may show the item small within a larger scene; find
the item first and ignore the background. Allow for different lighting, angle and distance. A visible
difference that couldn't plausibly change (a different logo, color or shape) should push the
score low. If there is too little visible detail to tell, say "unsure" rather than guessing.`;

function buildPrompt(
  report: Report,
  found: Found,
  reportPhoto: LoadedImage | null,
  foundPhoto: LoadedImage,
): ContentPart[] {
  const ownerText = `The owner's report: "${report.title}". Category ${report.category}, color ${report.color}. ` +
    `Description: ${report.description}`;
  const listingText = `The found listing: "${found.title}". Category ${found.category}, color ${found.color}. ` +
    `Description: ${found.description}`;

  if (reportPhoto) {
    return [
      text("Asset 0 is the owner's photo of the item they lost:"),
      image(toDataUrl(reportPhoto.bytes, reportPhoto.mime)),
      text("Asset 1 is a photo of an item found on campus:"),
      image(toDataUrl(foundPhoto.bytes, foundPhoto.mime)),
      text(`${ownerText}\n${listingText}\n\n${RULES}`),
    ];
  }
  return [
    text("This is a photo of an item found on campus:"),
    image(toDataUrl(foundPhoto.bytes, foundPhoto.mime)),
    text(
      `${ownerText}\n${listingText}\n\nThe owner has no photo, so compare the found photo with their ` +
        `written description. Without a photo, avoid scores above 85.\n\n${RULES}`,
    ),
  ];
}

/** Asks Perceptron how likely the report and listing are the same physical object. */
export async function compare(
  report: Report,
  found: Found,
  reportPhoto: LoadedImage | null,
  foundPhoto: LoadedImage,
): Promise<Rating> {
  const r = await askJson<Rating>(
    buildPrompt(report, found, reportPhoto, foundPhoto),
    "item_comparison",
    RATING_SCHEMA,
    768,
  );
  return consistent(r);
}

export type Sighting = { title: string; description: string; category: string; color: string };

const SIGHTING_RULES = `Both photos were taken by campus cameras near the same spot, possibly hours
apart and from different angles or distances. Judge whether they show the SAME physical object,
most likely an item still lying where it was left. Another copy of the same product nearby is a
different object: look for matching marks, wear, attachments and surroundings. The text descriptions
are automatically generated and may misname colors, logos or features: judge the PIXELS, not
conflicting text. A front view and a rear view can show different pockets/straps of the same bag.
Allow for lighting, exposure, angle and distance. A color difference under different lighting,
or straps/pockets visible in only one angle, is not by itself proof of a different object.
If there is too little common visible detail to tell, say "unsure" rather than "different".`;

/** Asks Perceptron whether a new sighting shows the same object as an existing listing. */
export async function compareSightings(
  fresh: Sighting,
  freshPhoto: LoadedImage,
  existing: Sighting,
  existingPhoto: LoadedImage,
  distanceM: number,
): Promise<Rating> {
  const describe = (s: Sighting) =>
    `"${s.title}". Category ${s.category}, color ${s.color}. Description: ${s.description}`;
  const r = await askJson<Rating>(
    [
      text("Asset 0 is an item already listed as found:"),
      image(toDataUrl(existingPhoto.bytes, existingPhoto.mime)),
      text("Asset 1 is an item just spotted:"),
      image(toDataUrl(freshPhoto.bytes, freshPhoto.mime)),
      text(
        `Listed item: ${describe(existing)}\nNew sighting: ${describe(fresh)}\n` +
          `They were recorded about ${Math.round(distanceM)} m apart.\n\n${SIGHTING_RULES}`,
      ),
    ],
    "sighting_comparison",
    RATING_SCHEMA,
    768,
  );
  return consistent(r);
}
