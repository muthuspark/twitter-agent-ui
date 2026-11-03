---
target: Feed navigation and thread buttons in supplied screenshot
total_score: 28
p0_count: 0
p1_count: 0
timestamp: 2026-11-03T16-09-22Z
slug: frontend-src-app-vue
---
**The buttons are clear, but too visually equal.** Refresh, Block list, and Close all use the same outlined treatment. A quieter hierarchy would better support reading.

**Anti-pattern verdict: pass.** The restrained colors, familiar icons, and Google Sans Flex work together. No obvious AI styling tells. The issue is overuse of the shared outlined button. The automated detector could not run because its bundled executable is missing; this is not a clean scan.

**Design health: 28/40, good.** This is a provisional score for these controls, not the whole app or an accessibility certification.

| Heuristic | Score | Finding |
|---|---:|---|
| System status | 3/4 | Refresh has loading feedback; Block list lacks a visible open state |
| Familiar language | 3/4 | Block list could imply accounts rather than phrases |
| User control | 3/4 | Clear Close and Escape support |
| Consistency | 3/4 | Consistent components, weak role hierarchy |
| Error prevention | 3/4 | Refresh disables while loading |
| Recognition | 3/4 | Clear text and familiar icons |
| Efficiency | 3/4 | Keyboard support and direct actions |
| Minimalist design | 2/4 | Utility outlines compete with reading |
| Error recovery | 3/4 | Adjacent retry; successful refresh not verified |
| Contextual help | 2/4 | Filter scope becomes clear only after opening |

**What works:** readable labels; consistent icon and type styling; native buttons with visible keyboard focus, an accessible Close name, and an expanded-state announcement for Block list. Keep these when simplifying the appearance.

**Priority issues**

1. **[P2] Block list has no persistent visible open state.** In Feeds.vue, aria-expanded changes but the resting appearance stays unchanged. Add a subtle token-based background or border state so users can see that filtering controls are open. Suggested command: `$impeccable polish`.
2. **[P2] Hit areas shrank with the font change.** Shared 2.75rem minimum height now measures 41.25px. Restore at least 44px without enlarging the 15px labels. Apply the same minimum to Close. This is a comfort recommendation, not a WCAG AA target-size failure. Suggested command: `$impeccable adapt`.
3. **[P3] Every action has equal visual weight.** Make Close a quiet icon button and Block list a quiet utility. Keep Refresh neutral with a light outline if desired. Reuse the existing button-quiet variant, preserving focus rings and hit areas. Suggested command: `$impeccable quieter`, followed by `$impeccable polish`.
4. **[P3] Block list is ambiguous.** The actual panel manages words and phrases, not blocked X accounts. “Blocked phrases” would communicate its scope more precisely. Suggested command: `$impeccable clarify`.

**Cognitive load and emotional journey:** low load, with two grouped toolbar actions and one local dismiss control. Hierarchy is the main checklist weakness. The reading experience is calm, but repeated outlines draw attention toward managing the interface. Close and Escape provide a reassuring exit.

**Persona checks:** Alex, a frequent reader, benefits from direct actions and Escape but gets unnecessary visual interruptions. Sam, a keyboard or motor-impaired user, benefits from accessible labels and focus rings; preserve these and restore the larger targets. Jordan, a newcomer, may mistake Block list for account blocking.

**Minor observations:** disabled buttons still match the shared hover background rule. Restrict hover styling to enabled buttons and add restrained pressed feedback.

**Questions to consider:** Can a utility remain discoverable without a permanent outline? Does the filter label communicate what users actually manage?
