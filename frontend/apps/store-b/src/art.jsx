// Bloom & Brew artwork: hand-drawn SVG illustrations, one per catalogue product, plus the logo and hero.
// Local and self-contained (no image downloads). Real product photos can replace any of these through
// `productImages` in main.jsx (slug → image URL), which takes priority over the illustration.
import React from 'react';

const C = {
  cream: '#f6ecdf', linen: '#ecdcc7', counter: '#e2cdb3', espresso: '#3b2418', coffee: '#6b4226', caramel: '#b8742a',
  kraft: '#c9a27a', milk: '#fbf5ec', sage: '#7d8f6a', leaf: '#5f7350', clay: '#c98b5e', glass: '#dbe7e8', steel: '#9aa3a6', honey: '#e0a12e',
};

// Shared backdrop: warm wall, a counter edge and a soft shadow, so every product sits on the same shelf.
function Scene({ children, shadow = [200, 254, 110, 12] }) {
  return (
    <svg viewBox="0 0 400 300" preserveAspectRatio="xMidYMid slice" aria-hidden="true" focusable="false">
      <rect width="400" height="300" fill={C.cream} />
      <circle cx="330" cy="70" r="90" fill={C.linen} opacity=".7" />
      <rect y="238" width="400" height="62" fill={C.counter} />
      <rect y="236" width="400" height="4" fill={C.kraft} opacity=".6" />
      <ellipse cx={shadow[0]} cy={shadow[1]} rx={shadow[2]} ry={shadow[3]} fill={C.espresso} opacity=".16" />
      {children}
    </svg>
  );
}

const Bean = ({ x, y, r = 0, fill = C.coffee }) => (
  <g transform={`translate(${x} ${y}) rotate(${r})`}>
    <ellipse rx="10" ry="14" fill={fill} />
    <path d="M0 -12 Q-5 0 0 12" fill="none" stroke={C.espresso} strokeWidth="2" />
  </g>
);

function CoffeeBag({ body, label, labelText, sub, accent }) {
  return (
    <Scene shadow={[200, 250, 90, 10]}>
      <path d="M134 74 H266 L276 246 H124 Z" fill={body} />
      <path d="M134 74 H266 L262 92 H138 Z" fill={C.espresso} opacity=".25" />
      <path d="M150 74 V62 H250 V74" fill={body} stroke={C.espresso} strokeWidth="3" />
      <rect x="146" y="118" width="108" height="92" rx="8" fill={label} />
      <text x="200" y="152" textAnchor="middle" fontFamily="Georgia, serif" fontSize="17" fontWeight="700" fill={C.espresso}>{labelText}</text>
      <text x="200" y="172" textAnchor="middle" fontFamily="Georgia, serif" fontSize="11" fill={C.coffee}>{sub}</text>
      <path d="M172 190 H228" stroke={accent} strokeWidth="4" strokeLinecap="round" />
      <Bean x={300} y={232} r={30} /><Bean x={92} y={236} r={-20} /><Bean x={112} y={226} r={50} fill={C.espresso} />
    </Scene>
  );
}

const Yirgacheffe = () => <CoffeeBag body={C.kraft} label={C.milk} labelText="ETHIOPIA" sub="Yirgacheffe · light" accent={C.honey} />;
const HouseBlend = () => <CoffeeBag body={C.espresso} label={C.linen} labelText="HOUSE" sub="Blend · medium-dark" accent={C.caramel} />;

const Sencha = () => (
  <Scene shadow={[200, 252, 80, 10]}>
    <rect x="140" y="92" width="120" height="152" rx="10" fill={C.sage} />
    <rect x="136" y="80" width="128" height="26" rx="8" fill={C.leaf} />
    <rect x="154" y="134" width="92" height="76" rx="6" fill={C.milk} />
    <text x="200" y="166" textAnchor="middle" fontFamily="Georgia, serif" fontSize="16" fontWeight="700" fill={C.leaf}>SENCHA</text>
    <path d="M186 192 Q200 170 216 186 Q202 200 186 192 Z" fill={C.leaf} />
    <path d="M188 192 L214 186" stroke={C.milk} strokeWidth="1.5" />
    <path d="M300 236 Q312 214 330 226 Q318 244 300 236 Z" fill={C.leaf} />
    <path d="M82 238 Q90 220 110 228 Q100 244 82 238 Z" fill={C.sage} />
  </Scene>
);

const Chai = () => (
  <Scene shadow={[200, 252, 100, 10]}>
    <path d="M150 84 H250 Q262 84 262 98 L270 246 H130 L138 98 Q138 84 150 84 Z" fill={C.clay} />
    <path d="M150 84 H250 L248 70 H152 Z" fill="#a56a42" />
    <rect x="152" y="128" width="96" height="78" rx="8" fill={C.milk} />
    <text x="200" y="162" textAnchor="middle" fontFamily="Georgia, serif" fontSize="18" fontWeight="700" fill={C.espresso}>CHAI</text>
    <text x="200" y="182" textAnchor="middle" fontFamily="Georgia, serif" fontSize="11" fill={C.coffee}>spiced black tea</text>
    <g transform="translate(300 230) rotate(-16)">
      <rect x="-34" y="-7" width="68" height="14" rx="7" fill="#8b5a33" />
      <rect x="-30" y="2" width="64" height="12" rx="6" fill="#a56a42" />
    </g>
    <g transform="translate(94 230)">
      {[0, 60, 120, 180, 240, 300].map((a) => <ellipse key={a} rx="5" ry="14" transform={`rotate(${a}) translate(0 -10)`} fill="#7a4a2a" />)}
      <circle r="5" fill={C.espresso} />
    </g>
  </Scene>
);

const Grinder = () => (
  <Scene shadow={[200, 254, 90, 10]}>
    <path d="M160 58 H240 L226 116 H174 Z" fill={C.glass} stroke={C.steel} strokeWidth="3" />
    <path d="M168 84 H232 L226 112 H174 Z" fill={C.coffee} />
    <rect x="156" y="52" width="88" height="10" rx="4" fill={C.espresso} />
    <rect x="148" y="116" width="104" height="132" rx="14" fill={C.espresso} />
    <circle cx="200" cy="150" r="16" fill={C.steel} />
    <circle cx="200" cy="150" r="6" fill={C.espresso} />
    <path d="M200 134 V140" stroke={C.milk} strokeWidth="3" strokeLinecap="round" />
    <rect x="166" y="190" width="68" height="44" rx="6" fill={C.coffee} />
    <rect x="166" y="190" width="68" height="12" rx="4" fill={C.caramel} />
  </Scene>
);

const Kettle = () => (
  <Scene shadow={[200, 252, 120, 12]}>
    <rect x="128" y="226" width="144" height="18" rx="6" fill={C.espresso} />
    <path d="M140 226 Q132 150 168 128 H232 Q268 150 260 226 Z" fill={C.milk} stroke={C.steel} strokeWidth="3" />
    <path d="M178 128 Q200 108 222 128" fill={C.milk} stroke={C.steel} strokeWidth="3" />
    <circle cx="200" cy="112" r="6" fill={C.espresso} />
    <path d="M258 200 Q300 196 300 160 Q302 120 330 100 L334 108 Q312 128 312 162 Q310 210 262 216" fill={C.milk} stroke={C.steel} strokeWidth="3" />
    <path d="M144 150 Q100 150 104 190 Q108 214 140 212" fill="none" stroke={C.espresso} strokeWidth="12" strokeLinecap="round" />
    <path d="M150 196 H250" stroke={C.caramel} strokeWidth="3" opacity=".7" />
  </Scene>
);

const FrenchPress = () => (
  <Scene shadow={[200, 254, 80, 10]}>
    <path d="M200 46 V84" stroke={C.steel} strokeWidth="5" />
    <circle cx="200" cy="42" r="9" fill={C.espresso} />
    <rect x="148" y="80" width="104" height="14" rx="5" fill={C.steel} />
    <rect x="152" y="94" width="96" height="146" rx="6" fill={C.glass} opacity=".9" />
    <rect x="156" y="130" width="88" height="106" rx="4" fill={C.coffee} />
    <rect x="156" y="130" width="88" height="10" fill={C.caramel} opacity=".8" />
    <rect x="146" y="236" width="108" height="10" rx="4" fill={C.steel} />
    <path d="M148 120 H252 M148 200 H252" stroke={C.steel} strokeWidth="6" />
    <path d="M252 112 Q296 116 292 170 Q290 208 252 214" fill="none" stroke={C.espresso} strokeWidth="12" strokeLinecap="round" />
  </Scene>
);

const Dripper = () => (
  <Scene shadow={[200, 254, 90, 10]}>
    <path d="M146 196 H254 Q252 246 200 248 Q148 246 146 196 Z" fill={C.milk} stroke={C.steel} strokeWidth="2" />
    <path d="M254 206 Q282 210 278 228 Q274 240 252 236" fill="none" stroke={C.milk} strokeWidth="9" />
    <path d="M118 96 H282 L224 184 H176 Z" fill={C.clay} />
    {[146, 172, 200, 228, 254].map((x) => <path key={x} d={`M${x} 102 L${200 + (x - 200) * 0.35} 178`} stroke="#a56a42" strokeWidth="2.5" />)}
    <rect x="160" y="182" width="80" height="12" rx="4" fill="#a56a42" />
    <path d="M196 196 V214" stroke={C.coffee} strokeWidth="4" strokeLinecap="round" />
  </Scene>
);

const Mugs = () => {
  const mug = (x, y, body, glaze) => (
    <g transform={`translate(${x} ${y})`}>
      <path d="M44 22 Q78 22 76 46 Q74 66 44 66" fill="none" stroke={body} strokeWidth="9" />
      <path d="M0 0 H52 V74 Q52 86 40 86 H12 Q0 86 0 74 Z" fill={body} />
      <path d="M0 0 H52 V18 Q26 26 0 18 Z" fill={glaze} />
      <ellipse cx="26" cy="0" rx="26" ry="5" fill={C.espresso} opacity=".5" />
    </g>
  );
  return (
    <Scene shadow={[200, 256, 150, 12]}>
      {mug(68, 152, C.sage, C.leaf)}
      {mug(144, 140, C.clay, '#a56a42')}
      {mug(220, 152, C.milk, C.linen)}
      {mug(292, 164, C.coffee, C.espresso)}
    </Scene>
  );
};

const Honey = () => (
  <Scene shadow={[200, 254, 90, 10]}>
    <rect x="148" y="70" width="104" height="26" rx="6" fill={C.leaf} />
    <path d="M140 96 H260 Q270 96 270 112 V230 Q270 246 252 246 H148 Q130 246 130 230 V112 Q130 96 140 96 Z" fill={C.honey} />
    <path d="M144 112 V226" stroke="#f5c76a" strokeWidth="8" strokeLinecap="round" opacity=".7" />
    <rect x="156" y="138" width="88" height="66" rx="8" fill={C.milk} />
    <text x="200" y="168" textAnchor="middle" fontFamily="Georgia, serif" fontSize="15" fontWeight="700" fill={C.espresso}>HONEY</text>
    <text x="200" y="186" textAnchor="middle" fontFamily="Georgia, serif" fontSize="10" fill={C.coffee}>raw wildflower</text>
    <g transform="translate(306 214) rotate(-35)">
      <rect x="-4" y="-60" width="8" height="70" rx="4" fill="#a56a42" />
      {[0, 10, 20].map((d) => <rect key={d} x="-14" y={10 + d} width="28" height="7" rx="3.5" fill="#8b5a33" />)}
    </g>
  </Scene>
);

export const productArt = {
  'ethiopia-yirgacheffe-beans': Yirgacheffe,
  'house-blend-beans': HouseBlend,
  'sencha-green-tea': Sencha,
  'spiced-chai-blend': Chai,
  'precision-burr-grinder': Grinder,
  'gooseneck-kettle': Kettle,
  'classic-french-press': FrenchPress,
  'ceramic-pour-over-dripper': Dripper,
  'stoneware-mug-set': Mugs,
  'wildflower-honey': Honey,
};

export function Logo() {
  return (
    <svg viewBox="0 0 48 48" aria-hidden="true" focusable="false">
      <circle cx="24" cy="24" r="23" fill="#f6ecdf" />
      <path d="M12 22 H34 V30 Q34 38 23 38 Q12 38 12 30 Z" fill="#3b2418" />
      <path d="M34 25 Q40 25 39 30 Q38 34 33 33" fill="none" stroke="#3b2418" strokeWidth="2.5" />
      <path d="M22 18 Q18 12 23 8 Q26 13 22 18 Z" fill="#7d8f6a" />
      <path d="M24 18 Q29 13 33 16 Q29 20 24 18 Z" fill="#b8742a" />
    </svg>
  );
}

export function HeroArt() {
  return (
    <svg viewBox="0 0 480 320" aria-hidden="true" focusable="false">
      <rect width="480" height="320" rx="20" fill="#ecdcc7" />
      <circle cx="380" cy="64" r="120" fill="#f6ecdf" opacity=".8" />
      <rect y="246" width="480" height="74" fill="#d9bf9f" />
      <path d="M190 120 Q178 96 194 76 Q206 58 194 40 M240 118 Q228 92 244 72 Q256 54 244 34" fill="none" stroke="#fbf5ec" strokeWidth="7" strokeLinecap="round" opacity=".9" />
      <ellipse cx="220" cy="262" rx="130" ry="14" fill="#3b2418" opacity=".18" />
      <ellipse cx="220" cy="252" rx="120" ry="18" fill="#fbf5ec" />
      <path d="M138 140 H302 V200 Q302 252 220 252 Q138 252 138 200 Z" fill="#3b2418" />
      <ellipse cx="220" cy="140" rx="82" ry="14" fill="#6b4226" />
      <ellipse cx="220" cy="140" rx="70" ry="9" fill="#b8742a" opacity=".6" />
      <path d="M302 158 Q352 158 350 192 Q348 222 300 222" fill="none" stroke="#3b2418" strokeWidth="14" strokeLinecap="round" />
      <g transform="translate(70 238) rotate(-20)"><ellipse rx="14" ry="20" fill="#6b4226" /><path d="M0 -17 Q-7 0 0 17" fill="none" stroke="#3b2418" strokeWidth="2.5" /></g>
      <g transform="translate(104 256) rotate(30)"><ellipse rx="12" ry="17" fill="#3b2418" /><path d="M0 -14 Q-6 0 0 14" fill="none" stroke="#1f120b" strokeWidth="2.5" /></g>
      <path d="M380 250 Q384 200 420 186 Q412 232 380 250 Z" fill="#7d8f6a" />
      <path d="M392 252 Q360 210 330 214 Q350 248 392 252 Z" fill="#5f7350" />
    </svg>
  );
}
