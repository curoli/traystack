import { artifactUrl, artifactViewUrl } from "../api";

export default function OriginalActions({ id }: { id: string }) {
  return (
    <span className="original-actions">
      <a href={artifactViewUrl(id)} target="_blank" rel="noopener noreferrer">
        View original ↗
      </a>
      <a className="download" href={artifactUrl(id)}>
        Download original ↓
      </a>
    </span>
  );
}
