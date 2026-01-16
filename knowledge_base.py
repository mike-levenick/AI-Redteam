"""
Simple knowledge base for the AI using keyword and heading-based search
Loads markdown files from a knowledge directory
"""

import os
import glob
import re

class KnowledgeBase:
    def __init__(self, knowledge_dir="/app/knowledge"):
        self.knowledge_dir = knowledge_dir
        self.documents = {}
        self.sections = {}

        if os.path.exists(knowledge_dir):
            self._load_documents()

    def _load_documents(self):
        """Load all markdown files from knowledge directory"""
        for filepath in glob.glob(f"{self.knowledge_dir}/**/*.md", recursive=True):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Tag if file is in restricted/ subdirectory
                    self.documents[filepath] = {
                        'content': content,
                        'restricted': '/restricted/' in filepath
                    }
                    # Extract sections by headers
                    self._index_sections(filepath, content)
            except Exception as e:
                print(f"Error loading {filepath}: {e}")

    def _index_sections(self, filepath, content):
        """Split document into sections based on markdown headers"""
        # Match ## Header or # Header
        sections = re.split(r'\n(#{1,3})\s+(.+)', content)

        current_section = ""
        current_title = os.path.basename(filepath)
        is_restricted = '/restricted/' in filepath

        for i in range(0, len(sections), 3):
            text = sections[i].strip()
            if text:
                key = f"{filepath}:{current_title}"
                self.sections[key] = {
                    'title': current_title,
                    'content': text,
                    'source': filepath,
                    'restricted': is_restricted
                }

            # Get next header if exists
            if i + 2 < len(sections):
                current_title = sections[i + 2].strip()

    def search(self, query, max_results=3, max_chars=2000, allow_restricted=False):
        """
        Search for relevant sections using keyword matching
        Returns list of (score, title, content, source) tuples
        """
        if not self.sections:
            return []

        query_lower = query.lower()
        # Use 3+ char keywords to catch short terms
        keywords = [w for w in re.findall(r'\w+', query_lower) if len(w) > 2]

        results = []

        for key, section in self.sections.items():
            # Skip restricted content if not allowed
            if section.get('restricted', False) and not allow_restricted:
                continue

            content_lower = section['content'].lower()
            title_lower = section['title'].lower()

            score = 0

            # Check for exact title match (very high score)
            if query_lower in title_lower or title_lower in query_lower:
                score += 20

            # Score based on keyword matches
            for keyword in keywords:
                # Title matches worth more
                score += title_lower.count(keyword) * 3
                # Content matches
                score += content_lower.count(keyword)

            if score > 0:
                results.append((
                    score,
                    section['title'],
                    section['content'][:max_chars],
                    section['source']
                ))

        # Sort by score and return top results
        results.sort(reverse=True, key=lambda x: x[0])
        return results[:max_results]

    def get_context(self, query, max_chars=2000, allow_restricted=False):
        """
        Get formatted context string for injection into prompt
        """
        results = self.search(query, max_results=3, max_chars=max_chars, allow_restricted=allow_restricted)

        if not results:
            return None

        context_parts = []
        for score, title, content, source in results:
            context_parts.append(f"[From {title}]\n{content}")

        return "\n\n".join(context_parts)
