"""Short role-local promotion and actual public-query-plan checks."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from src import isolated_actor,role_broker
from src.mpc import ProtocolError
from src.model import binding as model_binding


class Checks(unittest.TestCase):
    def test_role_promotion_requires_matching_source_and_binding(self):
        sid='a'*32;attempt='b'*16;binding='c'*64;model_id='d'*32
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'s0';request=root/'build/requests'/sid;own=request/'S0';own.mkdir(parents=True)
            (root/'build/assets/S0').mkdir(parents=True)
            model=dict(model_id=model_id)
            ops=[dict(type='matmul'),dict(type='he_aggregate',cache_capture=True,cache_binding=binding,
                                           model=model,count=3),dict(type='matmul')]
            (request/'job-template.json').write_text(json.dumps(dict(operations=ops)))
            payload=dict(role=0,source_session=sid,binding=binding,model_id=model_id,
                         asset_hashes=dict(source='same'),shares=[1,2,3])
            (own/('first-layer-'+attempt+'.json')).write_text(json.dumps(payload))
            with patch.object(isolated_actor,'ROOT',root),patch.object(isolated_actor,'own_role',return_value='s0'),\
                 patch.object(isolated_actor,'policy',return_value={}),patch('src.hidden_cache.sources',return_value=payload['asset_hashes']):
                result=isolated_actor.operation('install_hidden',sid,attempt)
                self.assertTrue(result['installed'])
                installed=root/'build/assets/S0/hidden-state.json'
                self.assertEqual(json.loads(installed.read_text()),payload)
                self.assertEqual(installed.stat().st_mode&0o777,0o600)
            with patch.object(isolated_actor,'ROOT',root),patch.object(isolated_actor,'own_role',return_value='s0'),\
                 patch.object(isolated_actor,'policy',return_value={}),patch('src.hidden_cache.sources',return_value=dict(source='changed')):
                with self.assertRaisesRegex(ProtocolError,'HIDDEN_INSTALL_SOURCE_CHANGED'):
                    isolated_actor.operation('install_hidden',sid,attempt)

    def test_broker_switches_only_after_durable_cache_marker(self):
        nodes=[f'node-{index}' for index in range(7)]
        model=model_binding('f'*32,nodes,3,6,2,7)
        report=dict(dimensions=[7,3,6,2],publication=dict(models=[model]),
                    he_setup=dict(public=dict(shape=[7,6],node_order=nodes,
                                              column_order=[f'hidden-{index}' for index in range(6)])),
                    receiver_id='authorized',allowed_targets=[nodes[0]])
        targets=report['allowed_targets']
        with patch.object(role_broker,'report',return_value=report),\
             patch.object(role_broker,'policy',return_value=dict(allowed_targets=targets)),\
             patch.object(role_broker,'hidden_state',return_value=None):
            first=role_broker.plan();self.assertTrue(first[1]['cache_capture'])
        cache=dict(binding=first[1]['cache_binding'],source_session='e'*32)
        with patch.object(role_broker,'report',return_value=report),\
             patch.object(role_broker,'policy',return_value=dict(allowed_targets=targets)),\
             patch.object(role_broker,'hidden_state',return_value=cache):
            later=role_broker.plan()
        self.assertEqual(later[0]['type'],'load_hidden')
        self.assertEqual(later[1]['previous_slice'],[0,report['dimensions'][0]*report['dimensions'][2]])
        self.assertEqual(later[2:],first[3:])

    def test_cache_install_requires_completed_delivery(self):
        sid='a'*32;binding='b'*64
        with tempfile.TemporaryDirectory() as temporary:
            admin=Path(temporary)
            (admin/(sid+'-result.json')).write_text('{}')
            (admin/(sid+'-backend.json')).write_text(json.dumps(dict(attempt='c'*16)))
            state=dict(state='running')
            with patch.object(role_broker,'ADMIN',admin),patch.object(role_broker,'policy',return_value=dict(operator_uid=0)),\
                 patch.object(role_broker,'identity',return_value=SimpleNamespace(pw_uid=10)),\
                 patch.object(role_broker,'attested',return_value=True),patch.object(role_broker,'record',return_value=state),\
                 patch.object(role_broker,'registered',return_value=state),patch.object(role_broker,'quiet_roles'),\
                 patch.object(role_broker,'plan',return_value=[dict(type='matmul'),dict(cache_binding=binding)]),\
                 patch.object(role_broker,'actor',return_value=dict(binding=binding,source_session=sid)) as actor,\
                 patch.object(role_broker,'codehash',return_value='fixture'):
                with self.assertRaisesRegex(ProtocolError,'HIDDEN_INSTALL_COMPLETION'):
                    role_broker.command(dict(action='cache_install',sid=sid),10)
                actor.assert_not_called()
                state['state']='completed'
                result=role_broker.command(dict(action='cache_install',sid=sid),10)
                self.assertTrue(result['installed'])
                self.assertEqual(actor.call_count,2)
                self.assertEqual(json.loads((admin/'hidden-cache.json').read_text())['source_session'],sid)


if __name__=='__main__':unittest.main()
