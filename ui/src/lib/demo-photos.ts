export const demoPhotos = [
  {
    key: "backpack",
    title: "Black backpack",
    category: "Bags",
    image: require("../../assets/demo/backpack.jpg"),
  },
  {
    key: "keys",
    title: "Keys with black fob",
    category: "Keys",
    image: require("../../assets/demo/keys.jpg"),
  },
  {
    key: "headphones",
    title: "Black headphones",
    category: "Electronics",
    image: require("../../assets/demo/headphones.jpg"),
  },
  {
    key: "pouch",
    title: "Blue and gold pouch",
    category: "Bags",
    image: require("../../assets/demo/pouch.jpg"),
  },
  {
    key: "tablet",
    title: "Black tablet",
    category: "Electronics",
    image: require("../../assets/demo/tablet.jpg"),
  },
  {
    key: "card-holder",
    title: "Black card holder",
    category: "Accessories",
    image: require("../../assets/demo/card-holder.jpg"),
  },
] as const;
export function demoPhoto(title: string, category: string) {
  const name = title.toLowerCase();
  return demoPhotos.find((p) => name.includes(p.key))?.image;
}
