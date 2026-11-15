// The status line: what it says is kept as a function of the language, so that a change of language
// alone writes it again in the new one (a message of an earlier language is not left on the page).
export function createStatus(line: HTMLElement) {
  let current: () => string = () => "";
  const write = () => {
    line.textContent = current();
  };
  return {
    say(text: () => string) {
      current = text;
      write();
    },
    /** Writes what it says again, in the language in use. */
    refresh: write,
  };
}
