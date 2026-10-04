import { useState } from 'react';

interface Props {
  before: string;
  after: string;
  beforeLabel?: string;
  afterLabel?: string;
}

/** Two images stacked; the slider reveals `after` from the left. */
export function CompareSlider({ before, after, beforeLabel = 'Trước', afterLabel = 'Sau' }: Props) {
  const [position, setPosition] = useState(50);
  return (
    <div className="compare">
      <div className="compare-stage">
        <img src={before} alt={beforeLabel} />
        <img src={after} alt={afterLabel} className="compare-top" style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }} />
        <span className="compare-label left">{afterLabel}</span>
        <span className="compare-label right">{beforeLabel}</span>
      </div>
      <input
        type="range" min={0} max={100} value={position} aria-label="Thanh so sánh"
        onChange={(e) => setPosition(Number(e.target.value))}
      />
    </div>
  );
}
