// Summit Trail Co. artwork: hand-drawn SVG illustrations, one per catalogue product, plus the logo and hero.
// Local and self-contained (no image downloads). Real product photos can replace any of these through
// `productImages` in main.jsx (slug → image URL), which takes priority over the illustration.
import React from 'react';

const C = {
  mist: '#e8eee5', ridge: '#d6e0d2', ground: '#c9d6c4', forest: '#1f4d3a', moss: '#4d7c5a', olive: '#7a8b4f',
  orange: '#c2410c', ember: '#ea7a2c', sand: '#d9c7a3', charcoal: '#2b332e', steel: '#8a9399', slate: '#3f6e8c', white: '#fbfcf9',
};

// Shared backdrop: misty sky, a distant ridge line and a soft ground shadow, so every product sits in the same scene.
function Scene({ children, shadow = [200, 252, 130, 14] }) {
  return (
    <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <rect width="400" height="300" fill={C.mist} />
      <path d="M0 190 L60 150 L105 172 L170 118 L230 160 L285 128 L340 165 L400 140 V300 H0 Z" fill={C.ridge} />
      <rect y="232" width="400" height="68" fill={C.ground} opacity=".55" />
      <ellipse cx={shadow[0]} cy={shadow[1]} rx={shadow[2]} ry={shadow[3]} fill={C.charcoal} opacity=".14" />
      {children}
    </svg>
  );
}

const Tent2P = () => (
  <Scene>
    <path d="M80 250 Q200 70 320 250 Z" fill={C.orange} />
    <path d="M80 250 Q200 70 320 250" fill="none" stroke={C.charcoal} strokeWidth="5" strokeLinecap="round" />
    <path d="M118 250 Q200 118 282 250" fill="none" stroke={C.ember} strokeWidth="3" opacity=".7" />
    <path d="M168 250 Q200 160 232 250 Z" fill={C.forest} />
    <path d="M200 166 V250" stroke={C.sand} strokeWidth="2" strokeDasharray="5 5" />
    <path d="M80 250 L48 262 M320 250 L352 262 M200 160 L200 148" stroke={C.charcoal} strokeWidth="2" />
  </Scene>
);

const Tent4P = () => (
  <Scene shadow={[200, 254, 160, 14]}>
    <path d="M58 252 L92 132 L308 132 L342 252 Z" fill={C.moss} />
    <path d="M92 132 L200 96 L308 132 Z" fill={C.forest} />
    <path d="M58 252 L92 132 L308 132 L342 252" fill="none" stroke={C.charcoal} strokeWidth="5" strokeLinejoin="round" />
    <rect x="96" y="150" width="62" height="34" rx="4" fill={C.mist} opacity=".85" />
    <rect x="242" y="150" width="62" height="34" rx="4" fill={C.mist} opacity=".85" />
    <path d="M166 252 L176 160 H224 L234 252 Z" fill={C.forest} />
    <path d="M70 214 H330" stroke={C.orange} strokeWidth="8" />
  </Scene>
);

const SleepingBag = () => (
  <Scene shadow={[200, 250, 150, 12]}>
    <g transform="rotate(-8 200 190)">
      <path d="M56 160 Q56 128 96 126 L300 140 Q344 146 344 190 Q344 232 300 236 L96 248 Q56 250 56 214 Z" fill={C.slate} />
      <path d="M56 160 Q56 128 96 126 L130 128 Q112 186 130 246 L96 248 Q56 250 56 214 Z" fill={C.forest} />
      <ellipse cx="96" cy="187" rx="22" ry="30" fill={C.charcoal} opacity=".55" />
      {[160, 196, 232, 268, 304].map((x) => <path key={x} d={`M${x} 134 Q${x - 8} 190 ${x} 242`} fill="none" stroke={C.mist} strokeWidth="2.5" opacity=".55" />)}
      <path d="M132 188 L330 190" stroke={C.ember} strokeWidth="4" strokeLinecap="round" />
    </g>
  </Scene>
);

const SleepingPad = () => (
  <Scene shadow={[200, 252, 150, 12]}>
    <path d="M60 236 L120 150 L344 150 L290 236 Z" fill={C.orange} />
    {[0, 1, 2, 3, 4, 5, 6].map((i) => {
      const t = i / 7;
      return <path key={i} d={`M${60 + 60 * t + 0} ${236 - 86 * t} L${290 + 54 * t} ${236 - 86 * t}`} stroke={C.ember} strokeWidth="3" opacity=".8" />;
    })}
    <path d="M60 236 L120 150 L344 150 L290 236 Z" fill="none" stroke={C.charcoal} strokeWidth="4" strokeLinejoin="round" />
    <path d="M60 236 L290 236 L290 248 L60 248 Z" fill="#9a3410" />
    <rect x="300" y="152" width="16" height="10" rx="3" fill={C.charcoal} />
  </Scene>
);

const Backpack55 = () => (
  <Scene shadow={[200, 260, 90, 12]}>
    <rect x="132" y="58" width="136" height="196" rx="34" fill={C.forest} />
    <path d="M132 112 Q132 52 200 50 Q268 52 268 112 Z" fill={C.moss} />
    <rect x="152" y="130" width="96" height="74" rx="14" fill={C.olive} />
    <path d="M152 150 H248" stroke={C.charcoal} strokeWidth="3" />
    <rect x="112" y="150" width="26" height="80" rx="10" fill={C.moss} />
    <rect x="262" y="150" width="26" height="80" rx="10" fill={C.moss} />
    <path d="M118 236 Q200 262 282 236" fill="none" stroke={C.charcoal} strokeWidth="10" strokeLinecap="round" />
    <rect x="190" y="226" width="20" height="16" rx="3" fill={C.orange} />
    <path d="M200 50 V36" stroke={C.charcoal} strokeWidth="6" strokeLinecap="round" />
  </Scene>
);

const Daypack = () => (
  <Scene shadow={[200, 256, 80, 12]}>
    <path d="M140 250 V120 Q140 66 200 64 Q260 66 260 120 V250 Z" fill={C.slate} />
    <path d="M150 120 Q150 78 200 76 Q250 78 250 120" fill="none" stroke={C.mist} strokeWidth="4" strokeDasharray="2 6" />
    <rect x="160" y="160" width="80" height="70" rx="16" fill="#2f5873" />
    <path d="M172 178 H228" stroke={C.mist} strokeWidth="3" />
    <circle cx="232" cy="178" r="4" fill={C.orange} />
    <path d="M136 236 Q200 254 264 236" fill="none" stroke={C.charcoal} strokeWidth="8" strokeLinecap="round" />
  </Scene>
);

const Boots = () => (
  <Scene shadow={[200, 250, 140, 12]}>
    <g>
      <path d="M96 238 L100 112 Q102 92 124 92 L168 92 Q182 92 182 108 L184 176 Q236 180 268 196 Q296 210 296 232 L296 238 Z" fill="#7a4e2d" />
      <path d="M100 150 L184 150" stroke="#5b3920" strokeWidth="4" />
      <path d="M182 176 Q238 182 270 198" fill="none" stroke="#5b3920" strokeWidth="4" />
      {[108, 124, 140, 156].map((y) => <path key={y} d={`M150 ${y} L180 ${y + 6}`} stroke={C.ember} strokeWidth="3" strokeLinecap="round" />)}
      <path d="M90 236 H302 Q306 250 296 254 H96 Q86 250 90 236 Z" fill={C.charcoal} />
      {[108, 138, 168, 198, 228, 258].map((x) => <rect key={x} x={x} y="250" width="16" height="6" rx="2" fill={C.charcoal} />)}
      <path d="M100 112 Q102 92 124 92 L168 92" fill="none" stroke={C.sand} strokeWidth="6" strokeLinecap="round" />
    </g>
  </Scene>
);

const RainJacket = () => (
  <Scene shadow={[200, 262, 120, 12]}>
    <path d="M160 70 Q200 44 240 70 L300 100 L336 210 L300 222 L280 150 L280 252 H120 V150 L100 222 L64 210 L100 100 Z" fill={C.orange} />
    <path d="M168 72 Q200 30 232 72 Q200 96 168 72 Z" fill="#9a3410" />
    <path d="M200 86 V252" stroke={C.charcoal} strokeWidth="4" />
    <path d="M140 170 H176 M224 170 H260" stroke="#9a3410" strokeWidth="4" strokeLinecap="round" />
    <path d="M120 236 H280" stroke="#9a3410" strokeWidth="5" />
    <path d="M100 100 L120 150 M300 100 L280 150" stroke="#9a3410" strokeWidth="3" />
  </Scene>
);

const Stove = () => (
  <Scene shadow={[200, 262, 70, 10]}>
    <path d="M170 160 Q200 70 230 160 Q216 132 200 150 Q184 132 170 160 Z" fill={C.ember} />
    <path d="M186 158 Q200 112 214 158 Z" fill="#facc15" />
    <rect x="164" y="160" width="72" height="14" rx="4" fill={C.steel} />
    <path d="M150 160 L172 176 M250 160 L228 176 M200 156 V146" stroke={C.charcoal} strokeWidth="5" strokeLinecap="round" />
    <rect x="186" y="174" width="28" height="16" fill={C.charcoal} />
    <path d="M150 196 Q150 188 200 188 Q250 188 250 196 V248 Q250 258 200 258 Q150 258 150 248 Z" fill={C.forest} />
    <ellipse cx="200" cy="196" rx="50" ry="9" fill={C.moss} />
    <rect x="150" y="214" width="100" height="18" fill={C.orange} />
    <path d="M226 180 Q262 182 266 168" fill="none" stroke={C.steel} strokeWidth="5" strokeLinecap="round" />
  </Scene>
);

const Headlamp = () => (
  <Scene shadow={[200, 250, 120, 12]}>
    <path d="M240 168 L380 120 L380 236 Z" fill="#fde68a" opacity=".55" />
    <ellipse cx="170" cy="190" rx="110" ry="46" fill="none" stroke={C.forest} strokeWidth="16" />
    <ellipse cx="170" cy="190" rx="110" ry="46" fill="none" stroke={C.orange} strokeWidth="4" strokeDasharray="10 8" />
    <rect x="196" y="150" width="70" height="66" rx="16" fill={C.charcoal} />
    <circle cx="236" cy="183" r="22" fill="#fef3c7" stroke={C.steel} strokeWidth="5" />
    <circle cx="236" cy="183" r="9" fill="#fde68a" />
    <rect x="206" y="160" width="12" height="8" rx="2" fill="#dc2626" />
  </Scene>
);

export const productArt = {
  'ridgeline-2p-tent': Tent2P,
  'basecamp-4p-tent': Tent4P,
  'alpine-20f-sleeping-bag': SleepingBag,
  'featherlite-sleeping-pad': SleepingPad,
  'trailhead-55l-backpack': Backpack55,
  'daytrip-22l-daypack': Daypack,
  'granite-hiking-boots': Boots,
  'stormshell-rain-jacket': RainJacket,
  'pocketflame-stove': Stove,
  'lumen-300-headlamp': Headlamp,
};

export function Logo() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <circle cx="24" cy="24" r="23" fill="#f4f6f2" />
      <path d="M6 36 L18 18 L24 26 L30 16 L42 36 Z" fill="#1f4d3a" />
      <path d="M26.5 21 L30 16 L33.5 21 L31 20 L30 22 L28.5 20 Z" fill="#f4f6f2" />
      <circle cx="35" cy="12" r="4" fill="#c2410c" />
    </svg>
  );
}

export function HeroArt() {
  return (
    <svg viewBox="0 0 480 320" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id="st-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#f7d9a8" />
          <stop offset=".6" stopColor="#e9efe6" />
        </linearGradient>
      </defs>
      <rect width="480" height="320" rx="20" fill="url(#st-sky)" />
      <circle cx="356" cy="92" r="34" fill="#f59e0b" opacity=".85" />
      <path d="M0 210 L90 110 L150 170 L230 70 L320 180 L380 130 L480 200 V320 H0 Z" fill="#4d7c5a" />
      <path d="M200 102 L230 70 L262 108 L246 102 L232 116 L216 100 Z" fill="#f4f6f2" />
      <path d="M0 250 L120 190 L220 236 L330 186 L480 240 V320 H0 Z" fill="#1f4d3a" />
      {[[40, 262], [78, 250], [410, 262], [446, 252], [372, 270]].map(([x, y]) => (
        <path key={x} d={`M${x} ${y} L${x + 14} ${y - 44} L${x + 28} ${y} Z`} fill="#17382a" />
      ))}
      <path d="M190 300 Q240 214 290 300 Z" fill="#c2410c" />
      <path d="M226 300 Q240 266 254 300 Z" fill="#17231c" />
      <path d="M0 296 H480 V320 H0 Z" fill="#17382a" />
    </svg>
  );
}
