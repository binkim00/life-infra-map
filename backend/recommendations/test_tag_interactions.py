import hashlib

from django.test import TestCase, override_settings

from recommendations.management.commands.aggregate_place_tag_interactions import (
    aggregate_place_tag_interactions,
)
from recommendations.models import (
    Place,
    PlaceInteractionEvent,
    PlaceTag,
    PlaceTagEvidence,
)


@override_settings(ALLOWED_HOSTS=['localhost', 'testserver'])
class PlaceInteractionApiTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name='Interaction Cafe',
            category='cafe',
            address='Busan',
            lat=35.15,
            lng=129.06,
            source='test',
            external_id='interaction-1',
        )

    def test_anonymous_search_demand_hashes_session_key(self):
        response = self.client.post(
            '/api/recommendations/interactions/',
            data={
                'event_type': 'search',
                'event_key': 'search-event-1',
                'session_key': 'browser-session-1',
                'search_id': 'search-1',
                'query': 'quiet brunch cafe',
                'requested_tags': ['quiet', 'brunch'],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        event = PlaceInteractionEvent.objects.get()
        self.assertEqual(
            event.session_key,
            hashlib.sha256(b'browser-session-1').hexdigest(),
        )
        self.assertEqual(event.requested_tags, ['quiet', 'brunch'])
        self.assertIsNone(event.user_id)

    def test_event_key_makes_retries_idempotent(self):
        payload = {
            'event_type': 'click',
            'event_key': 'click-event-1',
            'session_key': 'browser-session-1',
            'search_id': 'search-1',
            'place_id': self.place.id,
            'place_key': 'db:{}'.format(self.place.id),
            'place_name': self.place.name,
        }
        first = self.client.post(
            '/api/recommendations/interactions/',
            data=payload,
            content_type='application/json',
        )
        second = self.client.post(
            '/api/recommendations/interactions/',
            data=payload,
            content_type='application/json',
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(PlaceInteractionEvent.objects.count(), 1)
        self.assertEqual(PlaceInteractionEvent.objects.get().place, self.place)

    def test_batch_rejects_tag_feedback_without_a_tag(self):
        response = self.client.post(
            '/api/recommendations/interactions/',
            data={
                'events': [{
                    'event_type': 'tag_confirm',
                    'session_key': 'browser-session-1',
                    'place_id': self.place.id,
                }],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(PlaceInteractionEvent.objects.count(), 0)

    def test_explicit_feedback_is_aggregated_immediately(self):
        response = self.client.post(
            '/api/recommendations/interactions/',
            data={
                'events': [
                    {
                        'event_type': 'tag_confirm',
                        'event_key': 'confirm-{}'.format(index),
                        'session_key': 'session-{}'.format(index),
                        'place_id': self.place.id,
                        'tag_name': 'quiet',
                    }
                    for index in range(3)
                ],
            },
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 201)
        place_tag = PlaceTag.objects.get(
            place=self.place,
            tag__name='quiet',
            source='user_verified',
        )
        self.assertEqual(place_tag.status, 'confirmed')
        self.assertTrue(place_tag.is_verified)


class PlaceInteractionAggregationTests(TestCase):
    def setUp(self):
        self.place = Place.objects.create(
            name='Aggregate Cafe',
            category='cafe',
            address='Busan',
            lat=35.16,
            lng=129.07,
            source='test',
            external_id='aggregate-1',
        )

    def event(self, event_type, session, *, tag_name='', requested_tags=None):
        return PlaceInteractionEvent.objects.create(
            event_type=event_type,
            session_key=session,
            place=self.place,
            place_key='db:{}'.format(self.place.id),
            place_name=self.place.name,
            tag_name=tag_name,
            requested_tags=requested_tags or [],
        )

    def test_three_distinct_confirmations_create_verified_evidence(self):
        for index in range(3):
            self.event('tag_confirm', 'session-{}'.format(index), tag_name='quiet')

        stats = aggregate_place_tag_interactions()

        place_tag = PlaceTag.objects.get(
            place=self.place,
            tag__name='quiet',
            source='user_verified',
        )
        self.assertEqual(stats['explicit_groups'], 1)
        self.assertEqual(place_tag.status, 'confirmed')
        self.assertTrue(place_tag.is_verified)
        self.assertEqual(PlaceTagEvidence.objects.count(), 3)

    def test_behavior_requires_five_distinct_actors_and_stays_candidate(self):
        for index in range(5):
            self.event(
                'click',
                'session-{}'.format(index),
                requested_tags=['brunch'],
            )

        stats = aggregate_place_tag_interactions()

        place_tag = PlaceTag.objects.get(
            place=self.place,
            tag__name='brunch',
            source='interaction_signal',
        )
        self.assertEqual(stats['behavioral_groups'], 1)
        self.assertEqual(place_tag.status, 'candidate')
        self.assertFalse(place_tag.is_verified)
