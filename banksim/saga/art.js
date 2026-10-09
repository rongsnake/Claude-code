/* =====================================================================
   art.js : the drawn things of "The Long Ledger"
   ---------------------------------------------------------------------
   1. ART motifs (Object.assign over deck.js ART). 22 small scenes on a
      64x64 grid, built only from the shared class vocabulary
      (default fill, .lt outline, .ln line, .w heavy, .lt2 faint), so the
      woodcut, engraving, newsprint and terminal styles all still apply:
      crown (closed crown on a cushion), ship (carrack with planking,
      billowing courses, lateen, rigging, pennant and swell), plague
      (beaked doctor with wand, a marked door and a rat), fire (burning
      roofs), war (crossed pikes, morion, swallowtail banner, shot), riot
      (a crowd with raised fists at a bank's pedimented door), coin
      (stacked ducats and a struck coin), ledger (open book, quill,
      inkhorn), bubble (rising chart, bursting bubbles), quake (leaning
      tower, rent earth), flood (drowned roofs, spire, skiff, rain),
      letter (bill of exchange with quill and wafer), scales (balance
      with coins against a feather), cross (church front with rose
      window), seal (folded deed, ribbons, wax seal), train (4-4-0 engine,
      smoke, rails), telegraph (poles, wires, key, spark), screen
      (candlestick monitor), factory (sawtooth mill, stacks), gold
      (ingot pyramid), grain (sheaf and sickle), harbour (treadwheel
      crane, warehouse, lighthouse, moored hull).
   2. LedgerArt.titleScreen(): the opening page of an illuminated book:
      feTurbulence parchment, interlace border in blue and gold with red
      bosses, vine scrolls, a Lombardic initial T, and the house arms: a
      winged lion-beast holding an open ledger on a red shield above the
      motto scroll FIDES ET RATIO (an original design).
   3. LedgerArt.eraCard(): age announcements in five period manners:
      illuminated leaf, woodcut title page with printer's fleurons,
      copperplate cartouche, Victorian poster masthead, flat terminal.
   4. LedgerArt.portolanSymbols(): <symbol>s for the pre-1700 chart:
      sea serpent, 32-point rose with fleur-de-lis, gilt cartouche,
      galleon.
   ===================================================================== */
(function(){
'use strict';

Object.assign(ART,{
crown:'<path d="M5 56 Q32 64 59 56 Q61 60 57 62 Q32 68 7 62 Q3 60 5 56Z" class="lt2"/><path d="M13 44 Q32 49 51 44 L51 52 Q32 57 13 52Z" class="lt w"/><path d="M13 44 L10 24 Q19 33 22 20 Q26 31 32 15 Q38 31 42 20 Q45 33 54 24 L51 44" class="lt w"/><path d="M16 40 Q32 44 48 40 M22 21 Q25 33 23 43 M42 21 Q39 33 41 43 M32 16 V44" class="ln lt2"/><path d="M15 47 l2 4 M19 48 l2 4 M44 48 l2 4 M48 47 l2 4" class="ln lt2"/><circle cx="10" cy="22" r="2.4" class="lt"/><circle cx="22" cy="18" r="2.4" class="lt"/><circle cx="42" cy="18" r="2.4" class="lt"/><circle cx="54" cy="22" r="2.4" class="lt"/><ellipse cx="32" cy="50" rx="3.4" ry="2.4" class="lt w"/><ellipse cx="22" cy="49" rx="2" ry="1.6" class="lt"/><ellipse cx="42" cy="49" rx="2" ry="1.6" class="lt"/><path d="M32 2 V13 M27 6.5 H37" class="ln w"/><path d="M9 59 l-3 5 M55 59 l3 5" class="ln"/>',
ship:'<path d="M4 34 L16 35 L18 40 H47 L50 34 L60 32 Q57 46 47 51 H18 Q9 46 4 34Z" class="lt w"/><path d="M10 43 Q32 47 56 40 M14 47 Q32 50 52 46" class="ln lt2"/><path d="M22 41 v8 M30 41 v9 M38 41 v9 M46 41 v8" class="ln lt2"/><path d="M31 40 V5 M45 40 V15 M18 40 V17" class="ln w"/><path d="M22 10 H40 Q42 18 40 26 H22 Q20 18 22 10Z" class="lt"/><path d="M37 18 H52 Q54 24 52 30 H37" class="lt"/><path d="M18 18 L18 33 L8 33Z" class="lt"/><path d="M24 15 Q31 18 38 15 M24 21 Q31 24 38 21 M40 24 Q45 26 50 24" class="ln lt2"/><path d="M31 5 L4 30 M31 5 L59 30" class="ln lt2"/><path d="M31 1 V5 M31 1 Q37 1 42 3 Q37 5 31 5" class="lt"/><path d="M0 56 Q6 52 11 56 T21 56 T31 56 T41 56 T51 56 T64 56" class="ln w"/><path d="M5 61 Q10 58 15 61 T25 61 M37 61 Q42 58 47 61 T57 61" class="ln lt2"/>',
plague:'<path d="M2 62 V18 H14 V62" class="lt"/><path d="M8 26 V40 M4 31 H12" class="ln w"/><ellipse cx="34" cy="16" rx="15" ry="3.5" class="lt w"/><path d="M27 15 L28 5 Q34 3 40 5 L41 15" class="lt w"/><path d="M28 11 H40" class="ln"/><path d="M26 18 Q25 30 30 32 Q36 33 39 26 V18" class="lt w"/><path d="M38 21 Q50 25 58 38 Q50 33 38 29Z" class="lt w"/><path d="M42 25 L44 30 M47 28 L48 32" class="ln lt2"/><circle cx="33" cy="23" r="3" class="lt w"/><circle cx="33" cy="23" r="1"/><path d="M27 31 Q17 40 18 62 H48 Q48 42 39 30" class="lt w"/><path d="M24 42 L22 62 M28 38 L27 62 M33 36 V62 M38 38 L40 62 M43 44 L44 62" class="ln lt2"/><path d="M42 41 L57 30" class="ln w"/><circle cx="57" cy="29" r="1.8" class="lt"/><path d="M51 59 Q53 53 58 55 Q61 58 58 60Z" class="lt"/><path d="M51 59 Q44 61 44 56" class="ln"/><circle cx="58" cy="56.5" r=".8"/>',
fire:'<path d="M2 62 V40 L10 32 L18 40 V62 M20 62 V32 H34 V62 M38 62 V44 L48 36 L58 44 V62" class="lt w"/><path d="M5 44 l10 10 M22 36 l10 10 M22 46 l10 10 M41 48 l14 12" class="ln lt2"/><path d="M6 48 h4 v5 h-4Z M24 40 h3 v4 h-3Z M45 50 h5 v5 h-5Z"/><path d="M8 34 C2 26 10 20 9 11 C15 17 17 21 15 27 C19 23 19 19 18 15 C25 23 22 31 16 35Z" class="lt w"/><path d="M27 30 C21 20 28 13 26 3 C34 11 38 17 35 25 C39 21 39 17 38 13 C45 21 41 29 36 31Z" class="lt w"/><path d="M44 38 C38 30 46 25 44 17 C52 23 54 30 50 36Z" class="lt w"/><path d="M11 32 Q9 26 12 21 M30 28 Q28 20 30 13 M35 28 Q37 24 38 19 M47 35 Q45 30 47 25" class="ln"/><circle cx="20" cy="9" r="1"/><circle cx="47" cy="11" r="1.2"/><circle cx="57" cy="22" r="1"/><circle cx="3" cy="15" r="1"/><path d="M40 6 Q46 2 52 6 Q58 2 62 6" class="ln lt2"/><path d="M0 62 H64" class="ln w"/>',
war:'<path d="M2 58 H62" class="ln w"/><path d="M14 40 L46 22 L49 28 L18 48Z" class="lt w"/><path d="M22 40 l14 -8 M20 44 l22 -12" class="ln lt2"/><path d="M46 22 l3 -2 l4 7 l-4 1" class="lt"/><circle cx="22" cy="48" r="8" class="lt w"/><circle cx="22" cy="48" r="2"/><path d="M22 40 V56 M14 48 H30 M16 42 L28 54 M28 42 L16 54" class="ln lt2"/><path d="M8 54 L16 46" class="ln w"/><path d="M52 18 Q55 12 60 14 Q64 18 60 22 Q56 24 53 21" class="lt2"/><path d="M53 22 l3 -1 M56 18 l4 0 M55 14 l2 -3" class="ln lt2"/><circle cx="44" cy="54" r="3" class="lt"/><circle cx="51" cy="54" r="3" class="lt"/><circle cx="47.5" cy="49" r="3" class="lt"/><path d="M6 36 V4" class="ln w"/><path d="M6 4 Q14 7 22 4 V18 Q14 21 6 18" class="lt w"/><path d="M8 8 l12 8 M8 14 l8 5 M14 6 l7 5" class="ln lt2"/><circle cx="34" cy="10" r="1.5"/><path d="M30 14 l8 -8" class="ln lt2"/>',
riot:'<path d="M36 20 L50 10 L64 20" class="lt w"/><path d="M38 20 V58 M62 20 V58 M36 58 H64" class="ln w"/><path d="M44 58 V38 Q50 30 56 38 V58" class="lt"/><path d="M46 44 H54 M46 50 H54 M50 34 V58" class="ln lt2"/><path d="M42 24 h6 v6 h-6Z" class="lt"/><path d="M42 24 l3 3 l-2 3 M48 24 l-3 4" class="ln"/><circle cx="7" cy="42" r="4" class="lt w"/><circle cx="18" cy="37" r="4.5" class="lt w"/><circle cx="29" cy="42" r="4" class="lt w"/><path d="M1 64 Q1 48 7 48 Q13 48 13 64 M11 64 Q11 44 18 44 Q25 44 25 64 M23 64 Q23 48 29 48 Q35 48 35 64" class="lt w"/><path d="M4 54 l4 6 M14 52 l6 8 M26 54 l5 6" class="ln lt2"/><path d="M4 48 L2 34 M22 44 L25 25 M13 44 L10 30 M33 48 L36 34" class="ln w"/><circle cx="2" cy="32" r="1.8" class="lt"/><circle cx="10" cy="28" r="1.8" class="lt"/><circle cx="36" cy="32" r="1.8" class="lt"/><path d="M25 25 Q21 19 25 13 Q29 19 25 25Z" class="lt w"/><path d="M25 22 V17" class="ln"/><path d="M24 9 l-1 -3 M27 9 l2 -3" class="ln lt2"/>',
coin:'<ellipse cx="18" cy="56" rx="13" ry="4" class="lt w"/><path d="M5 50 V56 M31 50 V56" class="ln"/><ellipse cx="18" cy="50" rx="13" ry="4" class="lt"/><path d="M5 44 V50 M31 44 V50" class="ln"/><ellipse cx="18" cy="44" rx="13" ry="4" class="lt"/><path d="M7 38 V44 M29 38 V44" class="ln"/><ellipse cx="18" cy="38" rx="11" ry="3.6" class="lt"/><path d="M8 52 v4 M12 53 v4 M16 53 v4 M20 53 v4 M24 53 v4 M28 52 v4 M10 47 v3 M18 48 v3 M26 47 v3" class="ln lt2"/><circle cx="42" cy="26" r="19" class="lt w"/><circle cx="42" cy="26" r="15" class="lt"/><path d="M27 26 l-2 0 M57 26 l2 0 M42 11 v-2 M42 41 v2 M31 15 l-1.5 -1.5 M53 15 l1.5 -1.5 M31 37 l-1.5 1.5 M53 37 l1.5 1.5" class="ln"/><path d="M35 36 Q35 27 39 25 L42 17 L45 25 Q49 27 49 36Z" class="lt w"/><path d="M42 17 V12 M39.5 14 H44.5 M38 30 H46 M37 33 H47" class="ln"/><path d="M30 22 Q32 16 37 13" class="ln lt2"/>',
ledger:'<path d="M4 50 Q18 44 32 50 Q46 44 60 50 V54 Q46 49 32 55 Q18 49 4 54Z" class="lt w"/><path d="M6 46 V12 Q18 7 31 12 V48 Q18 43 6 46Z M58 46 V12 Q46 7 33 12 V48 Q46 43 58 46Z" class="lt w"/><path d="M10 18 Q18 15 27 18 M10 24 Q18 21 27 24 M10 30 Q18 27 27 30 M10 36 Q18 33 27 36 M37 18 Q45 15 54 18 M37 24 Q45 21 50 23 M37 30 Q45 27 54 30" class="ln lt2"/><path d="M21 14 V41 M48 14 V40" class="ln lt2"/><path d="M38 37 Q44 34 52 36" class="ln w"/><path d="M50 4 Q62 2 62 6 Q56 14 46 28 L44 30 L45 26 Q52 12 50 4Z" class="lt w"/><path d="M45 26 L57 6 M52 10 l4 1 M50 14 l4 1 M48 18 l3 1" class="ln lt2"/><path d="M8 58 H18 L16 63 H10Z" class="lt w"/><ellipse cx="13" cy="58" rx="5" ry="1.5"/>',
bubble:'<path d="M4 4 V60 H62" class="ln w"/><path d="M6 56 L14 52 L20 47 L26 40 L32 30" class="ln w"/><circle cx="40" cy="20" r="13" class="lt w"/><path d="M32 14 Q34 9 40 8" class="ln"/><circle cx="35" cy="12" r="1.3"/><path d="M32 30 Q38 22 44 26 Q48 20 50 16" class="ln lt2"/><path d="M54 8 l4 -4 M56 16 h6 M54 26 l5 3 M48 4 l1 -4" class="ln w"/><path d="M50 34 L52 44 L56 52 L62 58" class="ln w"/><path d="M50 34 l-3 1 M50 34 l1 -3" class="ln"/><circle cx="14" cy="30" r="5" class="lt"/><circle cx="22" cy="18" r="3" class="lt"/><circle cx="12" cy="30" r="1"/><path d="M8 60 v4 M18 60 v4 M28 60 v4 M38 60 v4 M48 60 v4 M58 60 v4" class="ln lt2"/>',
quake:'<path d="M14 48 L22 12 L34 14 L30 50Z" class="lt w"/><path d="M22 12 L22 6 L28 2 L34 8 V14" class="lt"/><path d="M21 20 h6 v6 h-6Z M19 32 h6 v6 h-6Z" class="lt"/><path d="M26 44 l3 -6 l-2 -4 l3 -5 l-1 -6" class="ln w"/><path d="M2 50 H22 L26 46 L30 52 M34 50 L38 46 L42 50 H62" class="ln w"/><path d="M30 52 L34 50 L33 64 L28 64Z" class="lt w"/><path d="M2 56 H62 M8 50 v14 M18 50 v14 M46 50 v14 M56 50 v14" class="ln lt2"/><path d="M42 26 l5 2 l-2 5 l-5 -2Z M50 36 l4 1 l-1 4 l-4 -1Z M44 16 l3 1 l-1 3 l-3 -1Z" class="lt w"/><path d="M8 40 l-5 -2 M8 34 h-6 M10 28 l-4 -3 M50 8 Q54 10 58 8 M48 12 Q54 15 60 12" class="ln lt2"/><circle cx="39" cy="44" r="1"/><circle cx="56" cy="46" r="1"/>',
flood:'<path d="M8 38 V22 L16 14 L24 22 V38 M36 36 V20 H46 V36" class="lt w"/><path d="M50 36 V18 L54 4 L58 18 V36" class="lt w"/><path d="M54 4 V0" class="ln"/><path d="M12 22 h4 v4 h-4Z M39 24 h4 v4 h-4Z" class="lt"/><path d="M0 36 Q8 30 16 36 T32 36 T48 36 T64 36" class="ln w"/><path d="M0 44 Q8 38 16 44 T32 44 T48 44 T64 44 M0 52 Q8 46 16 52 T32 52 T48 52 T64 52 M0 60 Q8 54 16 60 T32 60 T48 60 T64 60" class="ln lt2"/><path d="M22 32 Q30 36 40 32 L37 37 H25Z" class="lt w"/><path d="M31 33 V22 L37 29 H31" class="lt"/><circle cx="27" cy="31" r="1.4"/><path d="M4 2 l-2 6 M14 4 l-2 6 M24 2 l-2 6 M34 6 l-2 6 M44 2 l-2 6 M62 6 l-2 6" class="ln lt2"/>',
letter:'<path d="M6 12 H48 L56 20 V56 H6Z" class="lt w"/><path d="M48 12 V20 H56" class="lt"/><path d="M12 20 H36 M12 26 H44 M12 32 H50 M12 38 H40" class="ln lt2"/><path d="M12 48 Q16 42 20 48 T28 48 Q34 44 36 50" class="ln"/><path d="M10 15 h8" class="ln w"/><path d="M40 52 L36 62 L41 59 L43 63 L44 54" class="lt"/><circle cx="46" cy="47" r="6" class="lt w"/><circle cx="46" cy="47" r="3.2" class="lt"/><circle cx="46" cy="47" r="1"/><path d="M58 2 Q63 3 61 8 Q52 20 38 34 L36 36 L37 32 Q48 18 58 2Z" class="lt w"/><path d="M37 32 L58 5 M52 10 l4 1 M48 15 l4 1 M44 20 l3 1" class="ln lt2"/>',
scales:'<path d="M32 10 V56 M20 58 H44 M8 16 H56" class="ln w"/><path d="M24 58 Q32 52 40 58 V62 H24Z" class="lt w"/><circle cx="32" cy="8" r="3" class="lt w"/><path d="M28 16 L32 12 L36 16" class="lt"/><path d="M8 16 L3 36 M8 16 L13 36 M56 16 L51 32 M56 16 L61 32" class="ln"/><path d="M1 36 Q8 44 15 36Z M49 32 Q56 40 63 32Z" class="lt w"/><ellipse cx="8" cy="34" rx="4" ry="1.4" class="lt"/><ellipse cx="8" cy="31.5" rx="4" ry="1.4" class="lt"/><ellipse cx="8" cy="29" rx="4" ry="1.4" class="lt"/><path d="M50 30 Q56 22 62 26 Q56 28 50 30Z" class="lt"/><path d="M50 30 L60 25" class="ln lt2"/><path d="M27 59 v3 M31 57 v5 M35 57 v5 M28 26 h8 M28 42 h8" class="ln lt2"/>',
cross:'<path d="M29 2 H35 V8 H41 V14 H35 V22 H29 V14 H23 V8 H29Z" class="lt w"/><path d="M32 5 V19 M26 11 H38" class="ln lt2"/><path d="M8 62 V34 L32 22 L56 34 V62" class="lt w"/><circle cx="32" cy="38" r="7" class="lt w"/><path d="M32 31 V45 M25 38 H39 M27 33 L37 43 M37 33 L27 43" class="ln lt2"/><path d="M26 62 V54 Q32 46 38 54 V62" class="lt w"/><path d="M29 52 V62 M32 50 V62 M35 52 V62" class="ln lt2"/><path d="M14 52 V44 Q14 40 17 40 Q20 40 20 44 V52Z M44 52 V44 Q44 40 47 40 Q50 40 50 44 V52Z" class="lt"/><path d="M2 4 l8 6 M62 4 l-8 6 M14 0 l6 7 M50 0 l-6 7" class="ln lt2"/><path d="M4 62 H60" class="ln w"/>',
seal:'<path d="M4 10 H60 V44 H4Z" class="lt w"/><path d="M10 15 H40 M10 20 H50 M10 26 H54 M10 31 H34" class="ln lt2"/><path d="M26 44 L20 62 L25 59 L28 63 L31 48Z M38 44 L44 62 L39 59 L36 63 L33 48Z" class="lt w"/><path d="M25 50 l3 1 M24 54 l3 1 M39 50 l-3 1 M40 54 l-3 1" class="ln lt2"/><circle cx="32" cy="42" r="11" class="lt w"/><path d="M32 31 v3 M32 50 v3 M21 42 h3 M40 42 h3 M24 34 l2 2 M38 48 l2 2 M40 34 l-2 2 M24 50 l2 -2" class="ln"/><circle cx="32" cy="42" r="6" class="lt"/><path d="M29 45 L32 38 L35 45 M30 43 H34" class="ln"/><path d="M46 38 Q51 33 56 38" class="ln"/>',
train:'<path d="M2 58 H62" class="ln w"/><path d="M6 62 V58 M16 62 V58 M26 62 V58 M36 62 V58 M46 62 V58 M56 62 V58" class="ln lt2"/><path d="M12 30 H40 V46 H12Z" class="lt w"/><path d="M18 30 V46 M26 30 V46 M34 30 V46" class="ln lt2"/><path d="M40 20 H58 V46 H40Z" class="lt w"/><path d="M44 24 h10 v8 h-10Z" class="lt"/><path d="M42 36 h14 M42 40 h14" class="ln lt2"/><path d="M14 30 L12 16 H22 L20 30Z" class="lt w"/><path d="M26 30 Q26 24 30 24 Q34 24 34 30" class="lt"/><path d="M4 48 L12 40 V48Z" class="lt"/><circle cx="18" cy="50" r="6" class="lt w"/><circle cx="34" cy="50" r="6" class="lt w"/><circle cx="52" cy="52" r="4" class="lt w"/><path d="M18 50 H34 M18 44 V56 M34 44 V56" class="ln lt2"/><circle cx="18" cy="50" r="1.2"/><circle cx="34" cy="50" r="1.2"/><path d="M10 12 Q6 8 10 4 Q14 0 20 3 Q26 0 30 4 Q36 3 36 8 Q30 12 22 10 Q16 14 10 12Z" class="lt2"/>',
telegraph:'<path d="M10 62 V8 M46 62 V14" class="ln w"/><path d="M2 12 H18 M2 18 H18 M38 18 H54 M38 24 H54" class="ln"/><circle cx="4" cy="10" r="1.6"/><circle cx="16" cy="10" r="1.6"/><circle cx="4" cy="16" r="1.6"/><circle cx="16" cy="16" r="1.6"/><circle cx="40" cy="16" r="1.6"/><circle cx="52" cy="16" r="1.6"/><path d="M4 10 Q22 20 40 16 Q52 14 64 20 M16 16 Q34 28 52 22 Q58 21 64 26" class="ln lt2"/><path d="M29 2 L20 17 H27 L22 30 L35 12 H28Z" class="lt w"/><path d="M27 8 L24 14" class="ln lt2"/><path d="M22 54 H40 V60 H22Z" class="lt w"/><path d="M25 56 h3 M30 56 h3 M35 56 h3" class="ln lt2"/><path d="M26 54 L38 48" class="ln w"/><circle cx="40" cy="46" r="2" class="lt w"/><path d="M40 60 Q52 60 56 54 M2 62 H62" class="ln"/><path d="M44 42 l3 -2 M45 47 h3" class="ln lt2"/>',
screen:'<path d="M4 6 H60 V44 H4Z" class="lt w"/><path d="M8 10 H56 V40 H8Z" class="lt"/><path d="M8 20 H56 M8 30 H56" class="ln lt2"/><path d="M14 34 V22 M24 30 V16 M34 26 V12 M44 32 V16 M52 37 V27" class="ln"/><path d="M12 25 h4 v6 h-4Z M22 19 h4 v7 h-4Z M42 19 h4 v10 h-4Z" class="lt w"/><path d="M32 15 h4 v8 h-4Z M50 29 h4 v5 h-4Z"/><path d="M26 44 L24 54 H40 L38 44" class="lt w"/><path d="M28 47 h8 M28 50 h8" class="ln lt2"/><path d="M14 58 H50" class="ln w"/><path d="M8 62 h8 M20 62 h4 M28 62 h10 M42 62 h6" class="ln lt2"/>',
factory:'<path d="M2 58 V36 L12 28 V36 L22 28 V36 L32 28 V36 H40 V58Z" class="lt w"/><path d="M12 28 L4 36 M22 28 L14 36 M32 28 L24 36" class="ln lt2"/><path d="M44 58 L46 10 H54 L56 58Z" class="lt w"/><path d="M45 20 H55 M45 32 H55 M44 44 H56" class="ln"/><path d="M47 14 l2 4 M48 24 l2 6 M48 36 l2 6" class="ln lt2"/><path d="M6 42 h5 v5 h-5Z M16 42 h5 v5 h-5Z M26 42 h5 v5 h-5Z"/><path d="M33 48 h5 v10 h-5Z" class="lt"/><path d="M6 52 h22" class="ln lt2"/><path d="M50 10 Q44 6 48 2 Q52 -1 56 2 Q62 0 63 5 Q62 9 57 8 Q54 11 50 10Z" class="lt w"/><path d="M38 14 Q34 10 38 7 Q42 5 44 8" class="lt2"/><path d="M50 6 Q53 4 56 5" class="ln"/><path d="M0 60 H64" class="ln w"/>',
gold:'<path d="M2 58 L7 48 H27 L32 58Z M32 58 L37 48 H57 L62 58Z" class="lt w"/><path d="M7 48 L10 44 H30 L27 48 M37 48 L40 44 H60 L57 48" class="lt"/><path d="M17 44 L22 34 H42 L47 44Z" class="lt w"/><path d="M22 34 L25 30 H45 L42 34" class="lt"/><path d="M10 53 H24 M40 53 H54 M26 39 H38" class="ln"/><path d="M5 56 l4 -6 M35 56 l4 -6 M20 42 l4 -6" class="ln lt2"/><path d="M52 4 V20 M44 12 H60 M47 7 L57 17 M57 7 L47 17" class="ln w"/><circle cx="52" cy="12" r="1.5"/><path d="M14 18 V28 M9 23 H19" class="ln w"/><path d="M30 22 v4 M28 24 h4" class="ln"/><path d="M2 62 H62" class="ln"/>',
grain:'<path d="M32 62 V30 M32 62 L22 34 M32 62 L42 34 M32 62 L14 38 M32 62 L50 38" class="ln"/><path d="M25 48 Q32 44 39 48 V53 Q32 49 25 53Z" class="lt w"/><path d="M28 47 v5 M32 46 v5 M36 47 v5" class="ln lt2"/><ellipse cx="32" cy="18" rx="3.4" ry="10" class="lt w"/><ellipse cx="21" cy="22" rx="3" ry="9" transform="rotate(-20 21 22)" class="lt w"/><ellipse cx="43" cy="22" rx="3" ry="9" transform="rotate(20 43 22)" class="lt w"/><ellipse cx="12" cy="28" rx="2.8" ry="8" transform="rotate(-38 12 28)" class="lt"/><ellipse cx="52" cy="28" rx="2.8" ry="8" transform="rotate(38 52 28)" class="lt"/><path d="M29 14 l3 2 l3 -2 M29 20 l3 2 l3 -2 M18 18 l3 2 l2 -3 M41 17 l2 3 l3 -2" class="ln"/><path d="M32 8 V0 M21 13 L17 4 M43 13 L47 4 M8 21 L3 14 M56 21 L61 14" class="ln lt2"/><path d="M48 58 Q62 52 60 40 Q58 50 46 54Z" class="lt w"/><path d="M46 54 L40 60" class="ln w"/>',
harbour:'<path d="M0 46 H40 V52 H0Z" class="lt w"/><path d="M4 46 V52 M12 46 V52 M20 46 V52 M28 46 V52 M36 46 V52" class="ln lt2"/><path d="M0 56 Q6 52 12 56 T24 56 T36 56 T48 56 T64 56" class="ln w"/><path d="M0 62 Q6 58 12 62 T24 62 M36 62 Q42 58 48 62 T64 62" class="ln lt2"/><path d="M2 46 V24 L12 16 L22 24 V46" class="lt w"/><path d="M8 32 h8 v8 h-8Z" class="lt"/><path d="M12 16 V12" class="ln"/><path d="M28 46 V14 L44 8 M28 14 L40 24 V30" class="ln w"/><path d="M38 30 h5 v4 h-5Z" class="lt w"/><path d="M42 46 Q46 54 52 54 H60 Q64 50 64 44 L56 47 H44Z" class="lt w"/><path d="M52 47 V30 M52 32 L60 42 H52" class="ln"/><path d="M56 10 L58 2 L60 10 V24 H56Z" class="lt w"/><circle cx="58" cy="8" r="1"/><path d="M54 6 l-4 -2 M62 6 l4 -2" class="ln lt2"/>'
});

/* ---------------------------------------------------------- helpers */
const RM=()=>{try{return matchMedia('(prefers-reduced-motion: reduce)').matches;}catch(e){return false;}};
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const BL='"UnifrakturMaguntia","IM Fell English",Georgia,serif', FELL='"IM Fell English",Georgia,serif';
let uid=0;
function css(){
  if(document.getElementById('la-css'))return;
  const s=document.createElement('style'); s.id='la-css';
  s.textContent=`
.la-ov{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;background:radial-gradient(circle at 50% 40%,#3b2c1b,#140e08);color-scheme:light;transition:opacity .6s ease}
.la-ov.out{opacity:0}
.la-page{position:relative;width:min(94vw,70vh);aspect-ratio:3/4;container-type:inline-size;color:#2a1d10;box-shadow:0 10px 50px rgba(0,0,0,.7)}
.la-page>svg{position:absolute;inset:0;width:100%;height:100%;display:block}
.la-t1{position:absolute;left:41%;right:9%;top:12%;font-family:${BL};font-size:9.4cqw;line-height:1.02;color:#7a1712;margin:0;font-weight:400}
.la-t1 span{display:block;color:#1f3f8a}
.la-sub{position:absolute;left:15%;right:10%;top:33%;font-family:${FELL};font-style:italic;font-size:3.7cqw;line-height:1.35;text-align:center;margin:0}
.la-sub:first-letter{color:#7a1712;font-size:1.3em}
.la-btns{position:absolute;left:12%;right:12%;top:85%;display:flex;gap:3cqw;justify-content:center;flex-wrap:wrap}
.la-btn{font-family:${FELL};font-size:3.6cqw;padding:1.4cqw 3.4cqw;border:2px solid #b98a1e;border-radius:3px;background:#7a1712;color:#fbecc0;cursor:pointer;box-shadow:inset 0 0 0 2px #7a1712,inset 0 0 0 3px #e2b94a}
.la-btn.b{background:#1f3f8a;box-shadow:inset 0 0 0 2px #1f3f8a,inset 0 0 0 3px #e2b94a}
.la-btn:hover{filter:brightness(1.15)} .la-btn:focus-visible{outline:3px solid #e2b94a;outline-offset:3px}
.la-era{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;background:rgba(10,8,5,.82);cursor:pointer;color-scheme:light}
.la-era.anim{animation:la-fade var(--d) ease both}
.la-era.anim .la-card{animation:la-rise var(--d) ease both}
@keyframes la-fade{0%{opacity:0}14%{opacity:1}84%{opacity:1}100%{opacity:0}}
@keyframes la-rise{0%{transform:scale(.94) translateY(10px)}18%{transform:none}100%{transform:scale(1.02)}}
.la-card{position:relative;width:min(92vw,680px);aspect-ratio:16/10;container-type:inline-size;text-align:center;overflow:hidden}
.la-card>svg{position:absolute;inset:0;width:100%;height:100%}
.la-in{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:0 12%}
.la-in h2{margin:0;font-weight:400;line-height:1.05} .la-in p{margin:.4em 0 0}
.la-ms{color:#2a1d10} .la-ms h2{font-family:${BL};color:#7a1712;font-size:8.5cqw} .la-ms .s{font-family:${FELL};font-style:italic;font-size:3.4cqw} .la-ms .y{font-family:${FELL};color:#1f3f8a;font-size:3.6cqw;letter-spacing:.2em;font-variant:small-caps}
.la-wc{color:#16110a} .la-wc h2{font-family:${BL};font-size:8.6cqw} .la-wc .s{font-family:${FELL};font-size:3.3cqw} .la-wc .y{font-family:${FELL};font-size:3.4cqw;letter-spacing:.3em}
.la-en{color:#1d1a24} .la-en h2{font-family:${FELL};font-style:italic;font-size:7.4cqw} .la-en .s{font-family:${FELL};font-size:3.2cqw} .la-en .y{font-family:${FELL};font-size:3.2cqw;letter-spacing:.35em}
.la-vi{color:#141414} .la-vi .k{font-family:Georgia,serif;font-size:2.4cqw;letter-spacing:.5em;border-top:1px solid;border-bottom:1px solid;padding:.2em 1em} .la-vi h2{font-family:"Old Standard TT",Georgia,serif;font-weight:700;text-transform:uppercase;font-size:7.6cqw;letter-spacing:.04em;margin:.15em 0} .la-vi .s{font-family:"Old Standard TT",Georgia,serif;font-style:italic;font-size:3.2cqw} .la-vi .y{font-family:Georgia,serif;font-weight:700;font-size:3cqw;border:2px solid;padding:.1em .8em;margin-top:.6em}
.la-tm{color:#ffb000;font-family:"IBM Plex Mono",ui-monospace,monospace;text-align:left} .la-tm .la-in{align-items:flex-start;padding:0 9%} .la-tm .k{font-size:2.4cqw;color:#5fd3c4;letter-spacing:.1em} .la-tm h2{font-size:6.4cqw;text-transform:uppercase;letter-spacing:.02em;margin:.2em 0} .la-tm .s{font-size:2.8cqw;color:#e7d9b0} .la-tm .y{font-size:2.8cqw;color:#5fd3c4} .la-tm .c{display:inline-block;width:.6em;height:1em;background:#ffb000;vertical-align:-.15em;animation:la-blink 1s steps(1) infinite}
@keyframes la-blink{50%{opacity:0}}
@media (prefers-reduced-motion:reduce){.la-ov{transition:none}.la-tm .c{animation:none}}`;
  document.head.appendChild(s);
}

/* parchment fill + filter, ids unique per use */
function parch(id,w,h,base){
  return `<filter id="${id}" x="0" y="0" width="100%" height="100%"><feTurbulence type="fractalNoise" baseFrequency=".022 .03" numOctaves="4" seed="7"/><feColorMatrix values="0 0 0 0 .55  0 0 0 0 .42  0 0 0 0 .22  0 0 0 -1.1 .62"/><feComposite in2="SourceGraphic" operator="in"/><feBlend in2="SourceGraphic" mode="multiply"/></filter><radialGradient id="${id}v" cx=".5" cy=".5" r=".75"><stop offset=".6" stop-color="#7a5a2a" stop-opacity="0"/><stop offset="1" stop-color="#6a4a1e" stop-opacity=".45"/></radialGradient>`
  +`|<rect width="${w}" height="${h}" fill="${base||'#efdfb6'}" filter="url(#${id})"/><rect width="${w}" height="${h}" fill="url(#${id}v)"/>`;
}

/* vine scroll down a margin: stem, curls, leaves, berries */
function vine(x,y0,y1,amp){
  let d=`M${x} ${y0}`,o='';const cols=['#b3261e','#1f3f8a'];let k=0;
  for(let y=y0;y<y1;y+=56,k++){
    const s=k%2?1:-1;d+=` Q${x+s*amp} ${y+28} ${x} ${y+56}`;
    const cx=x+s*amp*.9,cy=y+28,c=cols[k%2];
    o+=`<path d="M${x+s*amp*.55} ${cy-6} q${s*14} -10 ${s*16} 4 q0 10 ${-s*9} 9 q-7 0 -6 -6 q2 -4 6 -2" fill="none" stroke="${c}" stroke-width="2.2"/>`;
    o+=`<path d="M${cx} ${cy+6} q${s*10} 6 ${s*6} 18 q${-s*10} -4 ${-s*6} -18Z" fill="${cols[(k+1)%2]}" stroke="#4a3010" stroke-width=".8"/>`;
    o+=`<circle cx="${cx+s*12}" cy="${cy-14}" r="3.4" fill="#d9a92a" stroke="#6b4a10" stroke-width=".8"/>`;
  }
  return `<path d="${d}" fill="none" stroke="#3f6b2a" stroke-width="2.6"/>`+o;
}

/* interlace band patterns (horizontal & vertical) */
function ilace(id){
  const t=`<rect width="24" height="20" fill="#1f3f8a"/><path d="M0 5 C6 5 6 15 12 15 S18 5 24 5 M0 15 C6 15 6 5 12 5 S18 15 24 15" fill="none" stroke="#1a1208" stroke-width="4.6"/><path d="M0 5 C6 5 6 15 12 15 S18 5 24 5" fill="none" stroke="#e2b94a" stroke-width="2.6"/><path d="M8 9 C10 12 11 14 12 15" fill="none" stroke="#1a1208" stroke-width="4.6"/><path d="M0 15 C6 15 6 5 12 5 S18 15 24 15" fill="none" stroke="#f3e6c4" stroke-width="2.6"/>`;
  return `<pattern id="${id}h" width="24" height="20" patternUnits="userSpaceOnUse">${t}</pattern><pattern id="${id}v" width="24" height="20" patternUnits="userSpaceOnUse" patternTransform="rotate(90)">${t}</pattern>`;
}
function boss(x,y){return `<rect x="${x-12}" y="${y-12}" width="24" height="24" fill="#d9a92a" stroke="#4a3010"/><path d="M${x} ${y-9} Q${x+5} ${y-5} ${x} ${y} Q${x-5} ${y-5} ${x} ${y-9}Z M${x} ${y+9} Q${x+5} ${y+5} ${x} ${y} Q${x-5} ${y+5} ${x} ${y+9}Z M${x-9} ${y} Q${x-5} ${y-5} ${x} ${y} Q${x-5} ${y+5} ${x-9} ${y}Z M${x+9} ${y} Q${x+5} ${y-5} ${x} ${y} Q${x+5} ${y+5} ${x+9} ${y}Z" fill="#b3261e" stroke="#4a3010" stroke-width=".8"/>`;}

/* the arms: red shield, winged beast with open ledger, motto scroll */
function arms(){
  const G='#d9a92a',K='#3a240c';
  return `<g stroke="${K}" stroke-linejoin="round" stroke-linecap="round">
<path d="M222 438 H378 V520 Q378 594 300 626 Q222 594 222 520Z" fill="${G}" stroke-width="2"/>
<path d="M232 448 H368 V520 Q368 586 300 614 Q232 586 232 520Z" fill="#9c1f17" stroke-width="1.5"/>
<path d="M240 456 l6 6 m10 -6 l6 6 m60 -6 l6 6 m10 -6 l6 6" stroke="#c4473a" stroke-width="1"/>
<path d="M306 506 Q314 470 352 460 Q346 470 354 474 Q344 480 352 488 Q340 492 348 500 Q334 502 340 512 Q326 510 318 520Z" fill="${G}" stroke-width="1.5"/>
<path d="M318 470 Q330 478 340 474 M316 486 Q330 492 344 488 M314 500 Q326 504 334 502" fill="none" stroke-width="1"/>
<path d="M276 530 Q282 506 304 506 Q330 506 338 532 Q350 556 342 580 L350 592 L330 592 L332 576 Q316 586 296 580 L296 592 L278 592 L284 574 Q270 556 276 530Z" fill="${G}" stroke-width="1.6"/>
<path d="M342 572 Q362 566 360 548 Q358 536 366 532 Q370 540 364 546" fill="none" stroke="${G}" stroke-width="4"/><path d="M342 572 Q362 566 360 548 Q358 536 366 532" fill="none" stroke-width="1"/>
<path d="M266 484 l8 -8 l4 6 l8 -6 l2 8 l9 -2 l-3 9 l8 3 l-7 6 l6 7 l-9 1 l1 9 l-8 -4 l-4 8 l-5 -7 l-8 4 l-1 -9 l-8 -2 l5 -7 l-6 -6 l9 -2Z" fill="#c48a12" stroke-width="1.2"/>
<circle cx="283" cy="497" r="13" fill="${G}" stroke-width="1.4"/>
<path d="M272 499 Q266 501 268 506 Q276 508 282 504 M277 494 h3 M276 506 l3 2" fill="none" stroke-width="1.4"/><circle cx="278" cy="494" r="1.4" fill="${K}"/>
<path d="M248 534 Q262 528 276 536 Q290 528 304 534 L300 562 Q288 556 276 564 Q264 556 252 562Z" fill="#f6ecd2" stroke-width="1.6"/>
<path d="M276 536 V564 M256 540 h14 M256 546 h14 M256 552 h12 M282 540 h16 M282 546 h16 M282 552 h10" fill="none" stroke-width=".9"/>
<path d="M262 528 Q268 520 276 524 Q284 520 290 528" fill="none" stroke="${G}" stroke-width="5"/>
<path d="M262 528 Q268 522 276 526 M290 528 Q284 522 276 526" fill="none" stroke-width="1"/>
</g>
<g stroke="#3a240c" stroke-width="1.5"><path d="M196 630 L214 618 L214 648 L196 660 L206 645Z M404 630 L386 618 L386 648 L404 660 L394 645Z" fill="#7a1712"/>
<path d="M210 616 Q300 640 390 616 V646 Q300 670 210 646Z" fill="#f3e6c4"/></g>
<text x="300" y="648" text-anchor="middle" font-family='${FELL}' font-size="14" letter-spacing="2" fill="#7a1712">FIDES · ET · RATIO</text>`;
}

/* ----------------------------------------------------------- title */
function titleScreen(opts){
  opts=opts||{}; css();
  const id='la'+(++uid), P=parch(id+'p',600,800).split('|');
  const T=`<g stroke="#4a3010"><rect x="92" y="82" width="148" height="148" fill="#d9a92a" stroke-width="2"/><rect x="100" y="90" width="132" height="132" fill="#1f3f8a" stroke-width="1"/>
<rect x="100" y="90" width="132" height="132" fill="url(#${id}d)" stroke="none"/>
<path d="M110 112 Q120 98 136 104 Q166 113 196 104 Q212 98 222 112 Q214 124 200 117 Q186 112 176 117 L173 196 Q173 208 186 211 L146 211 Q159 208 159 196 L156 117 Q146 112 132 117 Q118 124 110 112Z" fill="#b3261e" stroke="#e2b94a" stroke-width="2.4"/>
<path d="M166 120 V200" stroke="#f3c9a8" stroke-width="1.4"/>
<circle cx="116" cy="108" r="5" fill="#e2b94a"/><circle cx="216" cy="108" r="5" fill="#e2b94a"/>
<path d="M140 150 q-14 6 -20 20 q10 4 18 -6 M192 150 q14 6 20 20 q-10 4 -18 -6" fill="none" stroke="#e2b94a" stroke-width="2"/></g>`;
  const page=`<svg viewBox="0 0 600 800" preserveAspectRatio="none" aria-hidden="true"><defs>${P[0]}${ilace(id+'i')}<pattern id="${id}d" width="12" height="12" patternUnits="userSpaceOnUse"><path d="M6 0 L12 6 L6 12 L0 6Z" fill="none" stroke="#3a5aa8" stroke-width="1"/><circle cx="6" cy="6" r="1.3" fill="#e2b94a"/></pattern></defs>${P[1]}
<rect x="18" y="18" width="564" height="764" fill="none" stroke="#b3261e" stroke-width="3"/>
<rect x="30" y="30" width="540" height="20" fill="url(#${id}ih)"/><rect x="30" y="750" width="540" height="20" fill="url(#${id}ih)"/>
<rect x="30" y="30" width="20" height="740" fill="url(#${id}iv)"/><rect x="550" y="30" width="20" height="740" fill="url(#${id}iv)"/>
<rect x="30" y="30" width="540" height="740" fill="none" stroke="#4a3010" stroke-width="1.4"/><rect x="50" y="50" width="500" height="700" fill="none" stroke="#d9a92a" stroke-width="2"/>
${boss(40,40)}${boss(560,40)}${boss(40,760)}${boss(560,760)}${boss(300,40)}${boss(300,760)}
${vine(72,236,712,18)}
<path d="M240 156 Q256 160 262 176 M92 200 Q76 214 72 236" fill="none" stroke="#3f6b2a" stroke-width="2.6"/>
${T}
<path d="M150 420 H260 M340 420 H450" stroke="#d9a92a" stroke-width="2"/><path d="M300 412 l8 8 -8 8 -8 -8Z" fill="#b3261e" stroke="#4a3010"/>
${arms()}</svg>`;
  const ov=document.createElement('div');
  ov.className='la-ov'; ov.setAttribute('role','dialog'); ov.setAttribute('aria-modal','true'); ov.setAttribute('aria-labelledby',id+'h');
  ov.innerHTML=`<div class="la-page">${page}<h1 class="la-t1" id="${id}h"><span class="sr" style="position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)">T</span>he Long<span>Ledger</span></h1>
<p class="la-sub">A banking house, from a bench on the Rialto in 1300 to the list of banks that matter</p>
<div class="la-btns"><button type="button" class="la-btn" data-a="b">Begin in 1300</button>${opts.hasSave?'<button type="button" class="la-btn b" data-a="c">Continue the ledger</button>':''}</div></div>`;
  document.body.appendChild(ov);
  let gone=false;
  const close=fn=>{ if(gone)return; gone=true; document.removeEventListener('keydown',key,true);
    const fin=()=>{ov.remove(); if(typeof fn==='function')fn();};
    if(RM())fin(); else {ov.classList.add('out'); setTimeout(fin,600);} };
  const btns=[...ov.querySelectorAll('button')];
  btns.forEach(b=>b.addEventListener('click',()=>close(b.dataset.a==='c'?opts.onContinue:opts.onBegin)));
  function key(e){
    if(e.key==='Enter'){e.preventDefault();e.stopPropagation();(btns.includes(document.activeElement)?document.activeElement:btns[0]).click();}
    else if(e.key==='Tab'){const i=btns.indexOf(document.activeElement);e.preventDefault();btns[((i<0?-1:i)+(e.shiftKey?-1:1)+btns.length)%btns.length].focus();}
  }
  document.addEventListener('keydown',key,true);
  setTimeout(()=>btns[0].focus(),30);
  return {close:()=>close()};
}

/* ------------------------------------------------------- era cards */
const STY={rialto:'ms',medici:'ms',princes:'wc',northern:'wc',country:'en',lombard:'vi',basel:'tm'};
function fleuron(x,y,s,f){ // printer's leaf
  return `<g transform="translate(${x} ${y}) scale(${s}${f?' -1':''})"><path d="M0 0 C-14 -4 -22 -18 -10 -26 C-2 -30 6 -22 0 -14 C-4 -8 -10 -12 -8 -16 M0 0 C10 -2 22 2 26 -6 C30 -14 20 -18 16 -12" fill="none" stroke="currentColor" stroke-width="2.2"/><path d="M0 0 C-6 -10 -14 -12 -18 -20 C-8 -18 -2 -10 0 0Z" fill="currentColor"/></g>`;}
function eraArt(k,id){
  if(k==='ms'){const P=parch(id,800,500).split('|');
    return `<svg viewBox="0 0 800 500" preserveAspectRatio="none"><defs>${P[0]}${ilace(id+'i')}</defs>${P[1]}<rect x="20" y="20" width="760" height="16" fill="url(#${id}ih)"/><rect x="20" y="464" width="760" height="16" fill="url(#${id}ih)"/><rect x="20" y="20" width="16" height="460" fill="url(#${id}iv)"/><rect x="764" y="20" width="16" height="460" fill="url(#${id}iv)"/><rect x="44" y="44" width="712" height="412" fill="none" stroke="#d9a92a" stroke-width="2"/>${boss(28,28)}${boss(772,28)}${boss(28,472)}${boss(772,472)}<g stroke="#d9a92a" stroke-width="2"><path d="M250 330 H550"/></g><path d="M400 322 l8 8 -8 8 -8 -8Z" fill="#b3261e"/><circle cx="250" cy="330" r="4" fill="#1f3f8a"/><circle cx="550" cy="330" r="4" fill="#1f3f8a"/></svg>`;}
  if(k==='wc') return `<svg viewBox="0 0 800 500" preserveAspectRatio="none" style="color:#16110a"><rect width="800" height="500" fill="#efe3c2"/><rect x="16" y="16" width="768" height="468" fill="none" stroke="currentColor" stroke-width="9"/><rect x="34" y="34" width="732" height="432" fill="none" stroke="currentColor" stroke-width="2"/><path d="M34 70 H766 M34 430 H766" stroke="currentColor" stroke-width="1.5"/>${[0,1,2,3,4,5,6,7,8,9,10].map(i=>`<path d="M${70+i*66} 52 l10 -8 10 8 -10 8Z" fill="currentColor"/>`).join('')}${fleuron(380,448,.9)}${fleuron(420,448,.9,1)}${fleuron(320,140,1.1)}${fleuron(480,140,1.1,1)}<circle cx="400" cy="128" r="5" fill="currentColor"/><path d="M60 450 l12 -6 12 6 -12 6Z M716 450 l12 -6 12 6 -12 6Z" fill="currentColor"/></svg>`;
  if(k==='en') return `<svg viewBox="0 0 800 500" preserveAspectRatio="none" style="color:#1d1a24"><defs><pattern id="${id}h" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(40)"><path d="M0 0V4" stroke="currentColor" stroke-width=".9"/></pattern></defs><rect width="800" height="500" fill="#f6efdf"/><g fill="none" stroke="currentColor" stroke-width="1.6"><path d="M140 110 Q400 70 660 110 Q700 120 690 160 V340 Q700 380 660 390 Q400 430 140 390 Q100 380 110 340 V160 Q100 120 140 110Z"/><path d="M160 128 Q400 92 640 128 Q672 140 668 170 V330 Q672 360 640 372 Q400 408 160 372 Q128 360 132 330 V170 Q128 140 160 128Z" stroke-width=".8"/><path d="M110 160 Q60 150 64 112 Q70 82 100 90 Q120 100 108 116 Q96 122 92 110 M690 160 Q740 150 736 112 Q730 82 700 90 Q680 100 692 116 Q704 122 708 110 M110 340 Q60 350 64 388 Q70 418 100 410 Q120 400 108 384 Q96 378 92 390 M690 340 Q740 350 736 388 Q730 418 700 410 Q680 400 692 384 Q704 378 708 390"/><path d="M360 76 Q400 40 440 76 M380 70 Q400 54 420 70 M360 424 Q400 460 440 424"/><path d="M300 80 Q330 60 360 76 M500 80 Q470 60 440 76"/></g><path d="M64 112 Q70 82 100 90 Q86 98 84 116 Q76 128 64 112Z M736 112 Q730 82 700 90 Q714 98 716 116 Q724 128 736 112Z M64 388 Q70 418 100 410 Q86 402 84 384 Q76 372 64 388Z M736 388 Q730 418 700 410 Q714 402 716 384 Q724 372 736 388Z M140 390 Q400 430 660 390 Q400 418 140 390Z" fill="url(#${id}h)"/><path d="M380 336 H420 M300 336 H350 M450 336 H500" stroke="currentColor"/></svg>`;
  if(k==='vi') return `<svg viewBox="0 0 800 500" preserveAspectRatio="none" style="color:#141414"><defs><pattern id="${id}t" width="5" height="5" patternUnits="userSpaceOnUse"><circle cx="2.5" cy="2.5" r="1" fill="currentColor" opacity=".25"/></pattern></defs><rect width="800" height="500" fill="#ecebe4"/><rect width="800" height="500" fill="url(#${id}t)" opacity=".5"/><g stroke="currentColor" fill="none"><rect x="18" y="18" width="764" height="464" stroke-width="5"/><rect x="28" y="28" width="744" height="444" stroke-width="1"/><path d="M28 96 H772 M28 100 H772 M28 410 H772 M28 414 H772" stroke-width="1.5"/></g>${[1,2,3,4,5,6].map(i=>`<path d="M${i*110+15} 440 l3 7 7 0 -6 4 2 7 -6 -4 -6 4 2 -7 -6 -4 7 0Z" fill="currentColor"/>`).join('')}<path d="M60 58 h80 M660 58 h80" stroke="currentColor" stroke-width="3"/><path d="M60 66 h80 M660 66 h80" stroke="currentColor"/></svg>`;
  return `<svg viewBox="0 0 800 500" preserveAspectRatio="none"><rect width="800" height="500" fill="#0b0f0a"/><g stroke="#ffb000" stroke-opacity=".08">${[1,2,3,4,5,6,7,8,9].map(i=>`<path d="M${i*80} 0V500"/>`).join('')}${[1,2,3,4,5].map(i=>`<path d="M0 ${i*84}H800"/>`).join('')}</g><path d="M40 440 L140 420 L220 430 L320 380 L400 396 L500 330 L580 350 L680 280 L760 260" fill="none" stroke="#5fd3c4" stroke-width="2" opacity=".55"/><rect x="0" y="0" width="800" height="26" fill="#ffb000" opacity=".12"/><rect x="1" y="1" width="798" height="498" fill="none" stroke="#3a2c00" stroke-width="2"/></svg>`;
}
function eraCard(era,done){
  era=era||{}; css();
  const k=STY[era.id]||'ms', id='lae'+(++uid), rm=RM(), d=rm?1200:2200;
  const N=esc(era.name),S=esc(era.subtitle),Y=`${esc(era.start)}–${esc(era.end)}`;
  const inner = k==='vi'?`<div class="k">EXTRA · A NEW AGE · EXTRA</div><h2>${N}</h2><p class="s">${S}</p><p class="y">${Y}</p>`
    : k==='tm'?`<div class="k">&gt; REGIME_CHANGE // ${esc(String(era.id||'').toUpperCase())}</div><h2>${N}</h2><p class="s">${S}</p><p class="y">${Y} <span class="c"></span></p>`
    : k==='wc'?`<h2>${N}</h2><p class="s">${S}</p><p class="y">ANNO ${Y}</p>`
    : `<h2>${N}</h2><p class="s">${S}</p><p class="y">${Y}</p>`;
  const ov=document.createElement('div');
  ov.className='la-era'+(rm?'':' anim'); ov.style.setProperty('--d',d+'ms');
  ov.setAttribute('role','dialog'); ov.setAttribute('aria-label',`${era.name||''}, ${era.start||''} to ${era.end||''}`); ov.tabIndex=-1;
  ov.innerHTML=`<div class="la-card la-${k}">${eraArt(k,id)}<div class="la-in">${inner}</div></div>`;
  document.body.appendChild(ov);
  let fired=false,t;
  const fin=()=>{ if(fired)return; fired=true; clearTimeout(t); document.removeEventListener('keydown',key,true); ov.remove(); if(typeof done==='function')done(); };
  function key(e){ if(e.key==='Enter'||e.key==='Escape'||e.key===' '){e.preventDefault();e.stopPropagation();fin();} }
  ov.addEventListener('click',fin); document.addEventListener('keydown',key,true);
  t=setTimeout(fin,d); try{ov.focus({preventScroll:true});}catch(e){}
}

/* ---------------------------------------------------- portolan set */
function portolanSymbols(){
  const C='stroke="currentColor"';
  // sea serpent
  const monster=`<symbol id="s-monster" viewBox="0 0 60 30"><g class="pt-monster" ${C} stroke-width=".8" stroke-linejoin="round"><path d="M2 22 Q4 14 9 20 Q13 26 17 18 Q21 8 27 18 Q31 26 36 16 Q40 6 46 14 Q49 18 52 14 L50 18 Q46 22 44 18 Q39 12 37 20 Q32 30 26 22 Q21 14 18 22 Q13 30 8 24 Q5 21 2 22Z" fill="#a9c3a0"/><path d="M50 14 Q50 6 56 6 Q60 8 58 12 L54 13 L58 15 Q55 18 52 16Z" fill="#a9c3a0"/><circle cx="55" cy="9" r=".9" fill="currentColor"/><path d="M19 13 l1 -4 2 3 1 -4 2 3 M37 12 l1 -4 2 3 1 -4 2 3" fill="#d98a6a"/><path d="M2 22 Q-1 18 2 16 Q4 18 3 20" fill="none"/><path d="M8 22 q1 -1 2 0 M28 20 q1 -1 2 0 M40 15 q1 -1 2 0" fill="none" stroke-width=".5"/><path d="M0 28 q4 -2 8 0 t8 0 M30 28 q4 -2 8 0 t8 0 t8 0" fill="none" stroke-width=".5" opacity=".7"/></g></symbol>`;
  // 32-point rose
  const pts=[];
  for(let i=0;i<32;i++){const L=i%8==0?(i==0?36:44):i%4==0?36:i%2==0?28:21,w=i%8==0?6:i%4==0?5:i%2==0?3.5:2.5;pts.push({i,L,w});}
  pts.sort((a,b)=>a.L-b.L);
  let r='';const f=n=>n.toFixed(1);
  pts.forEach(({i,L,w})=>{const a=i*Math.PI/16,sx=Math.sin(a),cy=Math.cos(a),tx=50+L*sx,ty=50-L*cy,lx=50-w*cy,ly=50-w*sx,rx=50+w*cy,ry=50+w*sx;
    const cl=i%8==0?['#e8c96a','#b88a2a']:i%4==0?['#f1e4c4','#9c1f17']:i%2==0?['#f1e4c4','#3f6b2a']:['#f1e4c4','#1f3f8a'];
    r+=`<path d="M50 50 L${f(tx)} ${f(ty)} L${f(lx)} ${f(ly)}Z" fill="${cl[0]}"/><path d="M50 50 L${f(tx)} ${f(ty)} L${f(rx)} ${f(ry)}Z" fill="${cl[1]}" fill-opacity=".75"/>`;});
  const rose=`<symbol id="s-rose" viewBox="0 0 100 100"><g class="pt-rose" ${C} stroke-width=".4" stroke-linejoin="round"><circle cx="50" cy="50" r="46" fill="none" stroke-width=".6"/><circle cx="50" cy="50" r="40" fill="none" stroke-width=".3"/>${r}<circle cx="50" cy="50" r="4" fill="#e8c96a"/><circle cx="50" cy="50" r="1.5" fill="#9c1f17"/><path d="M50 2 Q54.5 8 50 14 Q45.5 8 50 2Z M50 12 Q56 3 61 9 Q56 8.5 52 14Z M50 12 Q44 3 39 9 Q44 8.5 48 14Z" fill="#9c1f17"/><path d="M44.5 14 H55.5" stroke-width="1.2"/><path d="M97 50 h-6 M94 47 v6" stroke-width=".9"/></g></symbol>`;
  const cart=`<symbol id="s-cartouche" viewBox="0 0 160 60"><g class="pt-cartouche" ${C} stroke-width=".8" stroke-linejoin="round"><path d="M22 8 H138 Q146 8 146 14 V46 Q146 52 138 52 H22 Q14 52 14 46 V14 Q14 8 22 8Z" fill="#f5ead0"/><path d="M26 12 H134 Q140 12 140 18 V42 Q140 48 134 48 H26 Q20 48 20 42 V18 Q20 12 26 12Z" fill="none" stroke-width=".4"/><path d="M14 14 Q2 12 3 24 Q4 32 12 30 Q16 26 12 22 Q8 22 9 26 M14 46 Q2 48 3 36 Q4 28 12 30 M146 14 Q158 12 157 24 Q156 32 148 30 Q144 26 148 22 Q152 22 151 26 M146 46 Q158 48 157 36 Q156 28 148 30" fill="#e8c96a"/><path d="M60 8 Q70 0 80 4 Q90 0 100 8 M60 52 Q70 60 80 56 Q90 60 100 52" fill="#e8c96a"/><circle cx="80" cy="4" r="2" fill="#9c1f17"/><circle cx="80" cy="56" r="2" fill="#9c1f17"/></g></symbol>`;
  const gal=`<symbol id="s-galleon" viewBox="0 0 40 40"><g class="pt-galleon" ${C} stroke-width=".6" stroke-linejoin="round"><path d="M3 24 L6 22 L9 26 H30 L32 21 L38 20 Q36 30 30 32 H10 Q5 30 3 24Z" fill="#8a5a2e"/><path d="M5 28 Q20 30 36 26" fill="none" stroke-width=".4"/><path d="M30 26 V20 H37 M6 22 V19 H10 V26" fill="#c79a5a"/><path d="M12 26 h2 M17 26 h2 M22 26 h2" stroke-width="1"/><path d="M20 26 V3 M28 26 V8 M11 26 V10 M32 21 L39 16" fill="none" stroke-width=".8"/><path d="M15 7 Q20 10 25 7 L25.5 15 Q20 18 14.5 15Z M15.5 16 Q20 19 25 16 L25 22 Q20 25 15 22Z M24 11 Q28 13 32 11 V18 Q28 20 24 18Z" fill="#f3ead6"/><path d="M11 11 L11 22 L5 22Z" fill="#f3ead6"/><path d="M20 3 L5 22 M20 3 L36 20 M28 8 L36 20" fill="none" stroke-width=".3"/><path d="M20 1 V3 M20 1.2 Q23 1.5 25 2.5 Q23 3 20 3" fill="#9c1f17"/><path d="M28 6.5 Q30 6.7 32 7.5 Q30 8 28 8" fill="#1f3f8a"/><path d="M0 34 q3 -2 6 0 t6 0 t6 0 t6 0 t6 0 t6 0 t6 0" fill="none" stroke-width=".5"/><path d="M4 37 q3 -2 6 0 t6 0 M24 37 q3 -2 6 0 t6 0" fill="none" stroke-width=".4" opacity=".6"/></g></symbol>`;
  return monster+rose+cart+gal;
}

window.LedgerArt={titleScreen,eraCard,portolanSymbols};
})();
