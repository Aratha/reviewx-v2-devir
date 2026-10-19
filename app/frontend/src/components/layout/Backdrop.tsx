import {useEffect, useRef} from 'react';

/**
 * The "Evren" backdrop: slow colour masses in the theme's cyan, violet and pink drift behind a
 * fine dot grid; the grid lights up in a soft circle around the pointer, and a faint grain keeps
 * the dark flat areas from banding. Everything is CSS (rules/32 tokens); this component only tells
 * the grid where the pointer is, at most once a frame. Purely decorative and hidden from assistive
 * technology; the masses stand still for users who prefer less motion.
 */
export function Backdrop() {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = root.current;
    if (!element) return;
    let frame = 0;
    let x = window.innerWidth * 0.6;
    let y = window.innerHeight * 0.3;

    function paint() {
      frame = 0;
      element!.style.setProperty('--spot-x', `${x}px`);
      element!.style.setProperty('--spot-y', `${y}px`);
    }

    function onPointer(event: PointerEvent) {
      x = event.clientX;
      y = event.clientY;
      if (!frame) frame = window.requestAnimationFrame(paint);
    }

    paint();
    window.addEventListener('pointermove', onPointer, {passive: true});
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('pointermove', onPointer);
    };
  }, []);

  return (
    <div ref={root} className="backdrop" aria-hidden="true">
      <div className="backdrop-mass backdrop-mass-1" />
      <div className="backdrop-mass backdrop-mass-2" />
      <div className="backdrop-mass backdrop-mass-3" />
      <div className="backdrop-dots" />
      <div className="backdrop-dots backdrop-dots-lit" />
      <div className="backdrop-grain" />
    </div>
  );
}
