// “Show me” in the help drawer and ?highlight= links both end here:
// scroll to the named element and pulse it for a few seconds.

export function highlightElement(id: string) {
	const element = document.getElementById(id);
	if (!element) return;
	element.scrollIntoView({ block: 'center' });
	element.classList.add('highlight-pulse');
	setTimeout(() => element.classList.remove('highlight-pulse'), 2600);
}
