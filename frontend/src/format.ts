// English display dates in the viewer's time zone, independent of browser locale.
export const formatDate = (value: string) =>
  new Date(value).toLocaleString("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    hour12: false,
  });
