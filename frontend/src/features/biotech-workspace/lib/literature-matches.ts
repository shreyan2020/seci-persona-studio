// Presentation-only: preserve stored search metadata and ranking inputs.
const generic = new Set(`a an the and or of for from in on at to by with without into through using use used uses study studies paper papers research result results first compare comparison evidence approach approaches method methods production produced producing produce improve improved improvement engineering engineered potential relevant relevance acid based`.split(/\s+/));

export function literatureMatches(labels: string[]): string[] {
  const terms: string[] = [], phrases: string[] = [];
  for (const label of labels) {
    const match = label.match(/^matched\s+(terms|phrases)\s*:\s*(.*)$/i);
    if (!match) continue;
    for (const raw of match[2].split(/[,;]/)) {
      const words = raw.trim().split(/\s+/);
      // Strip generic framing, while retaining domain phrases such as "itaconic acid".
      while (words.length && generic.has(words[0].toLowerCase())) words.shift();
      while (words.length && generic.has(words[words.length - 1].toLowerCase()) && words[words.length - 1].toLowerCase() !== 'acid') words.pop();
      const value = words.join(' ');
      if (!words.some(word => !generic.has(word.toLowerCase())) || !/[a-z]/i.test(value)) continue;
      (match[1].toLowerCase() === 'phrases' ? phrases : terms).push(value);
    }
  }
  const unique = (values: string[]) => values.filter((value, index) => values.findIndex(other => other.toLowerCase() === value.toLowerCase()) === index);
  const usefulPhrases = unique(phrases);
  return unique([...usefulPhrases, ...terms.filter(term => !usefulPhrases.some(phrase => phrase.toLowerCase().split(/\s+/).includes(term.toLowerCase()))) ]).slice(0, 6);
}
