import { FoundItem } from "../lib/types";

export interface CampusMapProps {
  items?: FoundItem[];
  pin?: { latitude: number; longitude: number };
  onPin?: (point: { latitude: number; longitude: number }) => void;
  onSelect?: (item: FoundItem) => void;
  center?: { latitude: number; longitude: number };
}
