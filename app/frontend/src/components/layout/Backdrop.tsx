import {useEffect, useRef} from 'react';

interface Star {
  x: number;
  y: number;
  r: number;
  drift: number;
  phase: number;
  tone: number;
}

/** Star colours come from the design tokens (rules/32); the canvas reads them once. */
const TONES = ['--color-star', '--color-star-cool', '--color-star-warm'];

/**
 * The "Evren" backdrop: a slow field of stars behind every page, over a softly moving nebula.
 * Purely decorative and hidden from assistive technology; it draws one still frame for users who
 * prefer less motion, pauses while the tab is hidden and stops when the page unmounts.
 */
export function Backdrop() {
  const canvas = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext('2d');
    if (!element || !context) return;
    const style = getComputedStyle(document.documentElement);
    const colours = TONES.map((name) => style.getPropertyValue(name).trim() || '#ffffff');
    const still = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    let stars: Star[] = [];
    let frame = 0;
    let width = 0;
    let height = 0;

    function resize() {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      element!.width = width * ratio;
      element!.height = height * ratio;
      context!.setTransform(ratio, 0, 0, ratio, 0, 0);
      const count = Math.round(Math.min(220, (width * height) / 7000));
      stars = Array.from({length: count}, () => ({
        x: Math.random() * width,
        y: Math.random() * height,
        r: Math.random() < 0.08 ? 1.3 + Math.random() * 0.9 : 0.4 + Math.random() * 0.8,
        drift: 0.015 + Math.random() * 0.05,
        phase: Math.random() * Math.PI * 2,
        tone: Math.floor(Math.random() * colours.length),
      }));
    }

    function draw(time: number) {
      context!.clearRect(0, 0, width, height);
      for (const star of stars) {
        if (!still) {
          star.y -= star.drift;
          if (star.y < -2) star.y = height + 2;
        }
        const twinkle = still ? 0.7 : 0.45 + 0.55 * Math.abs(Math.sin(time / 1800 + star.phase));
        context!.globalAlpha = twinkle * (star.r > 1.2 ? 0.95 : 0.6);
        context!.fillStyle = colours[star.tone];
        context!.beginPath();
        context!.arc(star.x, star.y, star.r, 0, Math.PI * 2);
        context!.fill();
      }
      context!.globalAlpha = 1;
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

  return <canvas ref={canvas} className="backdrop" aria-hidden="true" />;
}
