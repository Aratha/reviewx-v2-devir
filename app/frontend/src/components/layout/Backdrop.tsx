import {useEffect, useRef} from 'react';

interface Curtain {
  colour: string;
  /** Height of the curtain's lower edge as a share of the screen. */
  base: number;
  /** How far the lower edge sways up and down. */
  sway: number;
  /** Longest ray above the edge, as a share of the screen. */
  reach: number;
  speed: number;
  phase: number;
}

/** Curtain colours come from the design tokens (rules/32); the canvas reads them once. */
const TONES = ['--color-aurora-1', '--color-aurora-2', '--color-aurora-3'];
/** The aurora is softened with a blur, so it is drawn at a third of the screen's resolution. */
const SCALE = 1 / 3;

/**
 * The "Evren" backdrop: an aurora. Three upright curtains of light in the theme's cyan, violet
 * and pink stand across the screen from top to bottom; each is made of rays that brighten and fade
 * on their own, with a bright edge that sways slowly, the way a real aurora folds. Purely
 * decorative and hidden from assistive technology; one still frame for users who prefer less
 * motion; it pauses while the tab is hidden.
 */
export function Backdrop() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext('2d');
    if (!element || !context) return;
    const style = getComputedStyle(document.documentElement);
    const curtains: Curtain[] = TONES.map((name, index) => ({
      colour: style.getPropertyValue(name).trim() || '#7cf4ff',
      base: 0.34 + index * 0.24,
      sway: 0.035 + index * 0.01,
      reach: 0.2 - index * 0.025,
      speed: 0.00011 + index * 0.00004,
      phase: index * 2.4,
    }));
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    let frame = 0;
    let width = 0;
    let height = 0;

    function resize() {
      width = Math.max(1, Math.round(window.innerWidth * SCALE));
      height = Math.max(1, Math.round(window.innerHeight * SCALE));
      element!.width = width;
      element!.height = height;
    }

    function draw(time: number) {
      context!.setTransform(1, 0, 0, 1, 0, 0);
      context!.clearRect(0, 0, width, height);
      // The curtains hang vertically: draw them sideways and transpose the canvas.
      context!.setTransform(0, 1, 1, 0, 0, 0);
      const along = height;
      const across = width;
      context!.globalCompositeOperation = 'lighter';
      context!.lineWidth = 1.2;
      for (const curtain of curtains) {
        const t = time * curtain.speed + curtain.phase;
        for (let x = 0; x <= along; x++) {
          const u = x / along;
          // The lower edge folds: two slow waves and a faster ripple.
          const edge =
            across *
            (curtain.base +
              curtain.sway * Math.sin(u * 4.1 + t) +
              curtain.sway * 0.45 * Math.sin(u * 9.3 - t * 1.6) +
              0.008 * Math.sin(u * 40 + t * 3));
          // Each ray has its own height and brightness that drift over time.
          const ray = 0.55 + 0.45 * Math.sin(u * 23 + t * 2.2) * Math.sin(u * 7.7 - t * 1.3);
          const fade = Math.sin(Math.PI * Math.min(1, Math.max(0, u * 1.15 - 0.05)));
          const top = edge - across * curtain.reach * (0.45 + 0.55 * ray);
          const gradient = context!.createLinearGradient(0, top, 0, edge + 2);
          gradient.addColorStop(0, 'transparent');
          gradient.addColorStop(0.75, curtain.colour);
          gradient.addColorStop(0.97, curtain.colour);
          gradient.addColorStop(1, 'transparent');
          context!.globalAlpha = Math.max(0, ray) * fade * 0.55;
          context!.strokeStyle = gradient;
          context!.beginPath();
          context!.moveTo(x, top);
          context!.lineTo(x, edge + 2);
          context!.stroke();
        }
      }
      context!.globalAlpha = 1;
      context!.globalCompositeOperation = 'source-over';
      context!.setTransform(1, 0, 0, 1, 0, 0);
    }

    function loop(time: number) {
      draw(time);
      frame = window.requestAnimationFrame(loop);
    }

    function start() {
      window.cancelAnimationFrame(frame);
      if (still) draw(0);
      else if (!document.hidden) frame = window.requestAnimationFrame(loop);
    }

    function onResize() {
      resize();
      start();
    }

    resize();
    start();
    window.addEventListener('resize', onResize);
    document.addEventListener('visibilitychange', start);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', onResize);
      document.removeEventListener('visibilitychange', start);
    };
  }, []);

  return (
    <div className="backdrop" aria-hidden="true">
      <canvas ref={canvas} className="aurora" />
    </div>
  );
}
