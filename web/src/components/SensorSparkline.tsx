import type { SensorPointOut } from "../api/types";

export function SensorSparkline({
  readings,
  className = "h-8 w-full",
  stroke = "#F5A524",
}: {
  readings: SensorPointOut[];
  className?: string;
  stroke?: string;
}) {
  const values = readings
    .map((reading) => reading.value)
    .filter((value): value is number => value !== null);
  if (values.length < 2) return null;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const step = 100 / (values.length - 1);
  const points = values
    .map((value, index) => `${(index * step).toFixed(1)},${(26 - ((value - min) / span) * 24).toFixed(1)}`)
    .join(" ");
  return (
    <svg className={className} viewBox="0 0 100 28" preserveAspectRatio="none" aria-hidden="true">
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="1.8" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
