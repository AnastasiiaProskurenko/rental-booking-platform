from collections import defaultdict
from statistics import mean

from django.db import models
from django.db.models import Avg, Count
from apps.reviews.models import Review


def strict_reviewers(min_reviews=10, min_other_reviews=2):
    """
    Визначає 'строгих' клієнтів:
    тих, хто стабільно ставить нижче, ніж інші по тих самих listing
    """

    # 1) Середній рейтинг по listing
    listing_stats = dict(
        Review.objects
        .filter(rating__isnull=False, is_visible=True)
        .values('listing_id')
        .annotate(
            avg_rating=Avg('rating'),
            cnt=Count('id')
        )
        .values_list('listing_id', 'avg_rating', 'cnt')
    )
    # listing_id -> (avg_rating, cnt)

    # 2) Суми та кількість по (listing, reviewer)
    per_pair = (
        Review.objects
        .filter(rating__isnull=False, is_visible=True)
        .values('listing_id', 'reviewer_id')
        .annotate(
            sum_rating=models.Sum('rating'),
            cnt=models.Count('id')
        )
    )

    pair_map = {
        (row['listing_id'], row['reviewer_id']): (row['sum_rating'], row['cnt'])
        for row in per_pair
    }

    # 3) Обчислення diff = my_rating - others_avg
    diffs_by_reviewer = defaultdict(list)

    reviews = (
        Review.objects
        .filter(rating__isnull=False, is_visible=True)
        .values('listing_id', 'reviewer_id', 'rating')
    )

    for r in reviews:
        listing_id = r['listing_id']
        reviewer_id = r['reviewer_id']
        my_rating = r['rating']

        if listing_id not in listing_stats:
            continue

        listing_avg, listing_cnt = listing_stats[listing_id]
        my_sum, my_cnt = pair_map.get((listing_id, reviewer_id), (0, 0))

        other_cnt = listing_cnt - my_cnt
        if other_cnt < min_other_reviews:
            continue

        total_sum = float(listing_avg) * listing_cnt
        others_avg = (total_sum - my_sum) / other_cnt

        diff = float(my_rating) - float(others_avg)
        diffs_by_reviewer[reviewer_id].append(diff)

    # 4) Агрегація по reviewer
    result = []
    for reviewer_id, diffs in diffs_by_reviewer.items():
        if len(diffs) < min_reviews:
            continue

        harshness_index = mean(diffs)
        strong_negative_share = sum(d <= -1.0 for d in diffs) / len(diffs)

        result.append({
            "reviewer_id": reviewer_id,
            "reviews_used": len(diffs),
            "harshness_index": round(harshness_index, 3),
            "strong_negative_share": round(strong_negative_share, 3),
        })

    result.sort(key=lambda x: x["harshness_index"])
    return result

def compute_strict_reviewers(*, base_qs, min_reviews=10, min_other_reviews=2, limit=50):
    from collections import defaultdict
    from statistics import mean
    from django.db import models

    qs = base_qs.filter(rating__isnull=False, is_visible=True)

    # ✅ FIX: dict() не може прийняти 3-елементні кортежі напряму
    listing_stats = {
        listing_id: (avg_rating, cnt)
        for listing_id, avg_rating, cnt in (
            qs.values('listing_id')
              .annotate(avg_rating=Avg('rating'), cnt=Count('id'))
              .values_list('listing_id', 'avg_rating', 'cnt')
        )
    }

    per_pair = (
        qs.values('listing_id', 'reviewer_id')
          .annotate(sum_rating=models.Sum('rating'), cnt=Count('id'))
    )
    pair_map = {
        (row['listing_id'], row['reviewer_id']): (row['sum_rating'], row['cnt'])
        for row in per_pair
    }

    diffs_by_reviewer = defaultdict(list)
    for r in qs.values('listing_id', 'reviewer_id', 'rating'):
        listing_id = r['listing_id']
        reviewer_id = r['reviewer_id']
        my_rating = r['rating']

        if listing_id not in listing_stats:
            continue

        listing_avg, listing_cnt = listing_stats[listing_id]
        my_sum, my_cnt = pair_map.get((listing_id, reviewer_id), (0, 0))

        other_cnt = listing_cnt - my_cnt
        if other_cnt < min_other_reviews:
            continue

        total_sum = float(listing_avg) * int(listing_cnt)
        others_avg = (total_sum - float(my_sum)) / float(other_cnt)

        diffs_by_reviewer[reviewer_id].append(float(my_rating) - float(others_avg))

    result = []
    for reviewer_id, diffs in diffs_by_reviewer.items():
        if len(diffs) < min_reviews:
            continue
        harshness_index = mean(diffs)
        strong_negative_share = sum(d <= -1.0 for d in diffs) / len(diffs)

        result.append({
            'reviewer_id': reviewer_id,
            'reviews_used': len(diffs),
            'harshness_index': round(harshness_index, 3),
            'strong_negative_share': round(strong_negative_share, 3),
        })

    result.sort(key=lambda x: x['harshness_index'])
    return result[:limit]