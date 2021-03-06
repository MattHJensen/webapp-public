from django.test import TestCase
from django.test import Client
import mock

from ..models import BTaxSaveInputs, BTaxOutputUrl
from ...taxbrain.models import WorkerNodesCounter
from ..models import convert_to_floats
from ..compute import (DropqComputeBtax, MockComputeBtax,
                       MockFailedComputeBtax, NodeDownComputeBtax)
import taxcalc
from taxcalc import Policy


START_YEAR = 2016

OK_POST_DATA = {u'btax_betr_pass': 0.33,
                u'btax_depr_5yr': u'btax_depr_5yr_gds_Switch',
                u'btax_depr_27_5yr_exp': 0.4,
                u'has_errors': [u'False'],
                u'start_year': unicode(START_YEAR),
                u'csrfmiddlewaretoken': u'abc123'}

class BTaxViewsTests(TestCase):
    ''' Test the views of this app. '''
    expected_results_tokens = ['cost of capital', 'change from reform',
                               'baseline', 'reform',
                               'industry', 'asset', 'accommodation',
                               'typically financed', 'were generated on']
    def setUp(self):
        # Every test needs a client.
        self.client = Client()

    def test_btax_get(self):
        # Issue a GET request.
        response = self.client.get('/ccc/')

        # Check that the response is 200 OK.
        self.assertEqual(response.status_code, 200)

    def test_btax_post(self):
        #Monkey patch to mock out running of compute jobs
        import sys
        webapp_views = sys.modules['webapp.apps.btax.views']
        webapp_views.dropq_compute = MockComputeBtax()

        data = OK_POST_DATA.copy()

        response = self.client.post('/ccc/', data)
        # Check that redirect happens
        self.assertEqual(response.status_code, 302)
        # Go to results page
        link_idx = response.url[:-1].rfind('/')
        self.failUnless(response.url[:link_idx+1].endswith("ccc/"))

    def test_btax_nodes_down(self):
        #Monkey patch to mock out running of compute jobs
        import sys
        from webapp.apps.btax import views as webapp_views
        webapp_views.dropq_compute = NodeDownComputeBtax()

        data = OK_POST_DATA.copy()

        response = self.client.post('/ccc/', data)
        # Check that redirect happens
        self.assertEqual(response.status_code, 302)
        link_idx = response.url[:-1].rfind('/')
        self.failUnless(response.url[:link_idx+1].endswith("ccc/"))
        # One more redirect
        response = self.client.get(response.url)
        # Check that we successfully load the page
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)

    def test_btax_failed_job(self):
        #Monkey patch to mock out running of compute jobs
        import sys
        from webapp.apps.btax import views as webapp_views
        webapp_views.dropq_compute = MockFailedComputeBtax()
        data = OK_POST_DATA.copy()
        response = self.client.post('/ccc/', data)
        # Check that redirect happens
        self.assertEqual(response.status_code, 302)
        link_idx = response.url[:-1].rfind('/')
        print '302 response info', response.url, link_idx, str(response), response.url[:link_idx + 1]
        self.failUnless(response.url[:link_idx+1].endswith("ccc/"))
        response = self.client.get(response.url)
        # Make sure the failure message is in the response
        response = str(response)
        print 'test_btax_failed_job response', response
        self.failUnless("Your calculation failed" in response)

    def test_mocked_results_table(self):
        response = self.client.post('/ccc/mock-ccc-results')
        self.assertEqual(response.status_code, 200)
        response = str(response).lower()
        for expected in self.expected_results_tokens:
            self.assertIn(expected, response)

    def test_btax_submit_to_single_host(self):
        """
        Ensure that Btax submission does not advance the
        worker node counter, nor use the dropq_offset
        """

        # Set the worker node count to 1, which would error if we used
        # that for BTax, since there is only a single node
        wnc, created = WorkerNodesCounter.objects.get_or_create(singleton_enforce=1)
        wnc.current_offset = 1
        wnc.save()

        # Monkey patch to mock out running of compute jobs
        import sys
        webapp_views = sys.modules['webapp.apps.btax.views']
        webapp_views.dropq_compute = MockComputeBtax()
        data = OK_POST_DATA.copy()
        response = self.client.post('/ccc/', data)
        # Check that redirect happens
        self.assertEqual(response.status_code, 302)
        # Go to results page
        link_idx = response.url[:-1].rfind('/')
        self.failUnless(response.url[:link_idx+1].endswith("ccc/"))

        # Submit another job, which would error if we incremented dropq_offset
        # with the submit
        data = OK_POST_DATA.copy()
        response = self.client.post('/ccc/', data)
        # Check that redirect happens
        self.assertEqual(response.status_code, 302)

    def test_btax_edit_ccc_switches_show_correctly(self):
        #Monkey patch to mock out running of compute jobs
        import sys
        from webapp.apps.btax import views as webapp_views
        webapp_views.dropq_compute = MockComputeBtax()

        data = { u'has_errors': [u'False'],
                u'start_year': unicode(START_YEAR),
                u'btax_depr_5yr': u'btax_depr_5yr_ads_Switch',
                'csrfmiddlewaretoken':'abc123', u'start_year': u'2016'}

        response = self.client.post('/ccc/', data)
        # Check that redirect happens
        self.assertEqual(response.status_code, 302)
        # Go to results page
        link_idx = response.url[:-1].rfind('/')
        self.failUnless(response.url[:link_idx+1].endswith("ccc/"))
        model_num = response.url[link_idx+1:-1]
        edit_ccc = '/ccc/edit/{0}/?start_year={1}'.format(model_num, START_YEAR)
        edit_page = self.client.get(edit_ccc)
        self.assertEqual(edit_page.status_code, 200)

        # Get results model
        out = BTaxOutputUrl.objects.get(pk=model_num)
        bsi = BTaxSaveInputs.objects.get(pk=out.model_pk)
        assert bsi.btax_depr_5yr == u'btax_depr_5yr_ads_Switch'
        assert bsi.btax_depr_5yr_ads_Switch == 'True'
