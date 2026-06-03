export interface DeckPreviewSlide {
  slide_id: string;
  title?: string;
  headline?: string;
  materiality?: "high" | "medium" | "low" | string;
}

export interface DeckPreviewProps {
  slides?: DeckPreviewSlide[];
}

export function DeckPreview({ slides = [] }: DeckPreviewProps) {
  return (
    <section className="pfos-deck-preview" aria-labelledby="deck-preview-heading">
      <h2 id="deck-preview-heading">Deck preview</h2>
      {slides.length === 0 ? (
        <p>No deck slides loaded.</p>
      ) : (
        <ol>
          {slides.map((slide) => (
            <li key={slide.slide_id}>
              <strong>{slide.title ?? slide.headline ?? slide.slide_id}</strong>
              {slide.materiality ? <span>{slide.materiality}</span> : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export default DeckPreview;
