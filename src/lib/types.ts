export const categories = [
  "All",
  "Electronics",
  "Water Bottles",
  "Bags",
  "Keys",
  "Clothing",
  "Accessories",
  "Other",
] as const;
export type Category = Exclude<(typeof categories)[number], "All">;
export interface FoundItem {
  id: string;
  title: string;
  description: string;
  category: Category;
  color: string;
  image_path: string;
  image_paths: string[];
  approximate_location: string;
  latitude: number;
  longitude: number;
  source: "rover" | "community";
  status: string;
  discovered_at: string;
  pickup_location: string | null;
  is_demo: boolean;
}
export interface MissingReport {
  id: string;
  user_id: string;
  title: string;
  description: string;
  category: Category;
  color: string;
  image_path: string | null;
  last_seen_location: string;
  latitude: number;
  longitude: number;
  last_seen_at: string;
  status: string;
  created_at: string;
}
export interface Match {
  id: string;
  missing_report_id: string;
  found_item_id: string;
  match_score: number;
  match_reasons: string[];
  status: string;
  found_items: FoundItem;
  missing_reports: MissingReport;
}
export interface Profile {
  id: string;
  display_name: string;
  university_email: string | null;
  campus: string;
  avatar_url: string | null;
  notifications_enabled: boolean;
  university_verified: boolean;
}
export const campus = {
  latitude: 47.6553,
  longitude: -122.3035,
  latitudeDelta: 0.018,
  longitudeDelta: 0.018,
};
export const places = [
  { name: "Odegaard Library", latitude: 47.6566, longitude: -122.3102 },
  { name: "Red Square", latitude: 47.6559, longitude: -122.3093 },
  { name: "Husky Union Building", latitude: 47.6553, longitude: -122.3051 },
  { name: "Suzzallo Library", latitude: 47.6558, longitude: -122.308 },
  { name: "IMA", latitude: 47.6536, longitude: -122.301 },
];
