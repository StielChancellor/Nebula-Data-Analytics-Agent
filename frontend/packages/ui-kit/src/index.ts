/**
 * @insnav/ui-kit
 *
 * Headless React components consuming brand tokens via CSS vars.
 * The Aurora theme is the default; brand-runtime overrides tokens at runtime.
 *
 * TODO Phase 7+: implement the full kit (Button, Card, Dropdown, Modal,
 * SegmentedControl, Tooltip, KbdHint, Badge, Toast, SlideOver, ...).
 * Critically: a `<Portal>` + `<PositionedMenu>` pair so dropdowns never
 * get clipped by overflow:hidden ancestors (Nebula §6.5).
 */

export const UI_KIT_VERSION = "0.1.0";
