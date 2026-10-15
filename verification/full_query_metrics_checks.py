"""Short checks for public cost export and accepted full-query baseline."""
import unittest
from scripts.accept_full_inference import baseline,reference
from src.demo_coordinator import stage_summary
from src.isolated_actor import public_stages


class FullQueryMetricsChecks(unittest.TestCase):
    def test_private_worker_fields_are_not_exported(self):
        source=dict(operations=[dict(operation=0,type='he_aggregate',elapsed_seconds=1.25,bytes_sent=17,rounds=3,
                                     consumed={'secret_material':4},message_trace='private',
                                     components=[dict(name='convert',elapsed_seconds=.5,bytes_sent=7,rounds=1,he_profile={'secret':'x'},consumed={'secret_material':1})])])
        stage=public_stages(source)[0]
        self.assertEqual(set(stage),{'operation','type','elapsed_seconds','bytes_sent','rounds','components'})
        self.assertEqual(set(stage['components'][0]),{'name','elapsed_seconds','bytes_sent','rounds'})
        other=dict(stage,bytes_sent=19,components=[])
        row=stage_summary([dict(stages=[stage]),dict(stages=[other])])[0]
        self.assertEqual((row['wire_bytes'],row['rounds'],row['elapsed_seconds']),(36,3,1.25))

    def test_accepted_baseline_is_full_query(self):
        _,old,expected=reference();row=baseline(old)
        self.assertEqual(len(expected),7)
        self.assertEqual([s['type'] for s in row['online']['stages']],
                         ['matmul','he_aggregate','matmul','he_aggregate','precision_up','probability','deliver'])
        self.assertEqual(row['online']['wire_bytes'],96792628)


if __name__=='__main__':unittest.main()
