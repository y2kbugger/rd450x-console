// Extra keys: arrow keys and F1..F12 in noVNC's own "Extra keys" drawer.
//
// BIOS setup and boot menus are driven by arrows and function keys, which a
// browser tab often swallows (F5 reloads, F11 goes full screen, F1 opens help).
// The drawer already has Ctrl/Alt/Windows toggles, Tab, Esc and Ctrl-Alt-Del;
// this adds four arrow buttons and an "F1-F12" button that unfolds a grid of the
// function keys inside the same drawer. The held Ctrl/Alt toggles still apply, so
// e.g. Alt + F4 works.
//
// Keys go through noVNC's UI.sendKey (a press and release) with the physical key
// code, so the scancode pass-through in keyboard.js handles them like typed keys.

import UI from "../../app/ui.js";
import KeyTable from "../../core/input/keysym.js";
import { mkButton } from "./dom.js";

// arrowSvg draws a white arrow in noVNC's 25x25 icon box, pointing up, rotated
// by deg.
function arrowSvg(deg) {
  return (
    "data:image/svg+xml," +
    encodeURIComponent(
      "<svg xmlns='http://www.w3.org/2000/svg' width='25' height='25' viewBox='0 0 25 25'>" +
        `<g transform='rotate(${deg} 12.5 12.5)' fill='none' stroke='white' stroke-width='2.5' ` +
        "stroke-linecap='round' stroke-linejoin='round'>" +
        "<path d='M12.5 20V5M6 11.5l6.5-6.5 6.5 6.5'/></g></svg>",
    )
  );
}

const FKEYS_SVG =
  "data:image/svg+xml," +
  encodeURIComponent(
    "<svg xmlns='http://www.w3.org/2000/svg' width='25' height='25' viewBox='0 0 25 25'>" +
      "<rect x='1.5' y='4.5' width='22' height='16' rx='3' fill='none' stroke='white' stroke-width='1.5'/>" +
      "<text x='12.5' y='16.5' font-family='sans-serif' font-size='10' font-weight='bold' " +
      "fill='white' text-anchor='middle'>F1</text></svg>",
  );

const ARROWS = [
  ["Up", 0, KeyTable.XK_Up, "ArrowUp"],
  ["Down", 180, KeyTable.XK_Down, "ArrowDown"],
  ["Left", 270, KeyTable.XK_Left, "ArrowLeft"],
  ["Right", 90, KeyTable.XK_Right, "ArrowRight"],
];

export function build() {
  const drawer = document.getElementById("noVNC_modifiers");
  if (!drawer) return;

  for (const [name, deg, keysym, code] of ARROWS) {
    const b = mkButton("rd450x_send_" + code, "Send " + name, arrowSvg(deg));
    b.addEventListener("click", () => UI.sendKey(keysym, code));
    drawer.appendChild(b);
  }

  const toggle = mkButton("rd450x_toggle_fkeys", "Function keys", FKEYS_SVG);
  const grid = document.createElement("div");
  grid.id = "rd450x_fkeys";
  for (let n = 1; n <= 12; n++) {
    const b = document.createElement("input");
    b.type = "button";
    b.value = "F" + n;
    b.title = "Send F" + n;
    b.addEventListener("click", () => UI.sendKey(KeyTable["XK_F" + n], "F" + n));
    grid.appendChild(b);
  }
  toggle.addEventListener("click", () => {
    const open = grid.classList.toggle("rd450x_open");
    toggle.classList.toggle("noVNC_selected", open);
  });
  drawer.appendChild(toggle);
  drawer.appendChild(grid);
}
