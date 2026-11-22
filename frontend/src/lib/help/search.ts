// Instant help search: plain word overlap, no library and no AI.
// A title about a topic beats a passing mention in the text, words
// still being typed match by their start, and articles written for
// the page the person is on come first when the match is even.

export type Article = {
	id: string;
	title: string;
	body: string;
	pages: string[];
	keywords: string[];
	show_me?: { href: string; highlight: string };
};

function wordsOf(text: string): string[] {
	return text
		.toLowerCase()
		.split(/[^a-z0-9]+/)
		.filter((word) => word !== '');
}

// Ordinary question words appear in almost every article, so they
// must not count as a match on their own (“How do I …?”).
const QUESTION_WORDS = new Set([
	'a', 'an', 'the', 'i', 'me', 'my', 'we', 'you', 'your', 'it', 'its',
	'how', 'what', 'when', 'where', 'why', 'which', 'who',
	'do', 'does', 'did', 'can', 'could', 'should', 'would', 'will',
	'is', 'are', 'was', 'were', 'to', 'of', 'in', 'on', 'for', 'with',
	'and', 'or', 'this', 'that', 'there', 'please'
]);

function matches(word: string, token: string): boolean {
	return word === token || word.startsWith(token);
}

function fieldScore(text: string, tokens: string[], weight: number): number {
	const words = wordsOf(text);
	let score = 0;
	for (const token of tokens) {
		if (words.some((word) => matches(word, token))) score += weight;
	}
	return score;
}

function keywordScore(keywords: string[], tokens: string[]): number {
	let score = 0;
	for (const token of tokens) {
		if (keywords.some((keyword) => wordsOf(keyword).some((word) => matches(word, token)))) {
			score += 3;
		}
	}
	return score;
}

export function searchArticles(articles: Article[], query: string, page = ''): Article[] {
	const onThisPage = (article: Article) => (page !== '' && article.pages.includes(page) ? 1 : 0);
	// A question with no word left over behaves like no question yet.
	const tokens = wordsOf(query).filter((word) => !QUESTION_WORDS.has(word));

	if (tokens.length === 0) {
		return [...articles].sort((a, b) => onThisPage(b) - onThisPage(a));
	}

	return articles
		.map((article, index) => {
			const matched =
				fieldScore(article.title, tokens, 5) +
				keywordScore(article.keywords, tokens) +
				fieldScore(article.body, tokens, 1);
			return {
				article,
				index,
				matched,
				// Help written for this page gets real priority, not just a
				// tie-break — but the boost never creates a match by itself.
				score: matched + onThisPage(article) * 4
			};
		})
		.filter((entry) => entry.matched > 0)
		.sort(
			(a, b) =>
				b.score - a.score || onThisPage(b.article) - onThisPage(a.article) || a.index - b.index
		)
		.map((entry) => entry.article);
}
