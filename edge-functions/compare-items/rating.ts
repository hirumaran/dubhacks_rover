// Prompt, schema and Perceptron call for comparing a missing item with a found listing.
// Kept free of Supabase so it can be exercised directly.

import type { LoadedImage } from "../_shared/images.ts";
import { askJson, type ContentPart, image, text, toDataUrl } from "../_shared/perceptron.ts";

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
  return { ...r, similarity: Math.max(0, Math.min(100, Math.round(r.similarity))) };
}
