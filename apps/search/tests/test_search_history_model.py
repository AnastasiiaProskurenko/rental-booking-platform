
from django.test import TestCase
from apps.search.models import SearchHistory

class SearchHistoryTest(TestCase):

    def test_search_history_creation(self):
        s = SearchHistory.objects.create(query="Berlin", results_count=5)
        self.assertEqual(s.results_count, 5)
