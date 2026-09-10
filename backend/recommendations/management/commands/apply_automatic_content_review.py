"""Hash-pinned, resumable backlog processing with an exclusive preimage backup."""
import hashlib
import json
from collections import Counter
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from recommendations.models import EvidenceReview, PlaceTag, PlaceTagEvidence
from recommendations.services import automatic_content_review as policy
from recommendations.services.tag_evidence_aggregation import aggregate_tag_evidence


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--simulate", action="store_true")
        parser.add_argument("--backup-dir")
        parser.add_argument("--limit", type=int)

    def handle(self, *args, **options):
        manifest=json.loads(Path(options["manifest"]).read_text(encoding="utf-8-sig"))
        actual_hash=hashlib.sha256(Path(policy.__file__).read_bytes().replace(b"\r\n",b"\n")).hexdigest()
        if manifest.get("policy_hash")!=actual_hash:
            raise CommandError("Policy differs from preview")
        items=manifest["items"]
        if options["limit"] is not None:
            if options["limit"]<1:raise CommandError("Limit must be positive")
            items=items[:options["limit"]]
        if len({r['id'] for r in items})!=len(items) or not items:
            raise CommandError("Invalid manifest IDs")
        if options["apply"] and options["simulate"]:raise CommandError("Choose one mode")
        if options["apply"] and not options["backup_dir"]:raise CommandError("Backup directory required")
        ids=[r['id'] for r in items]
        counts=Counter();receipt=[]
        if options["apply"]:
            folder=Path(options["backup_dir"]);folder.mkdir(mode=0o700,parents=False,exist_ok=False)
            pairs=set(PlaceTagEvidence.objects.filter(pk__in=ids).values_list('place_id','tag_id'))
            queries={
                'originals':PlaceTagEvidence.objects.filter(pk__in=ids),
                'reviews':EvidenceReview.objects.filter(evidence_id__in=ids),
                'attestations':PlaceTagEvidence.objects.filter(evidence_key__in=[f'admin-review:{pk}' for pk in ids]),
                'tags':PlaceTag.objects.filter(place_id__in={p for p,t in pairs}),
            }
            for name,query in queries.items():
                with (folder/(name+'.jsonl')).open('x',encoding='utf-8') as handle:
                    for row in query.values().iterator(chunk_size=500):
                        if name=='tags' and (row['place_id'],row['tag_id']) not in pairs:continue
                        handle.write(json.dumps(row,ensure_ascii=False,default=str)+'\n')
            (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
        def process_batch(batch):
            touched={}
            for item in batch:
                row=PlaceTagEvidence.objects.select_for_update().select_related('place','tag').get(pk=item['id'])
                if (str(row.updated_at)!=item['observed_updated_at'] or hashlib.sha256(row.evidence.encode()).hexdigest()!=item['quote_hash']
                        or row.place_id!=item['place_id'] or row.tag_id!=item['tag_id']):
                    outcome='changed_skip'
                elif not options['apply'] and not options['simulate']:
                    outcome='eligible_'+item['decision']
                else:
                    outcome=policy.auto_review_content(row,decision=item['decision'],reason=item['reason'],run_key=manifest['run_key'])
                    if outcome not in ('preserved_manual','unchanged'):
                        touched[(row.place_id,row.tag_id)]=(row.place,row.tag)
                counts[outcome]+=1;receipt.append({'id':row.id,'outcome':outcome,'decision':item['decision']})
            for place,tag in touched.values():aggregate_tag_evidence(place,tag)
        if options['simulate']:
            with transaction.atomic():
                process_batch(items)
                transaction.set_rollback(True)
        else:
            for index in range(0,len(items),200):
                with transaction.atomic():process_batch(items[index:index+200])
                if options['apply']:
                    with (folder/'receipt.jsonl').open('a',encoding='utf-8') as handle:
                        for row in receipt[-len(items[index:index+200]):]:handle.write(json.dumps(row)+'\n')
                self.stdout.write(json.dumps({'type':'progress','processed':min(index+200,len(items)),'counts':dict(counts)}))
        approved=EvidenceReview.objects.filter(evidence_id__in=ids,status='approved').count()
        self.stdout.write(json.dumps({'type':'complete','run_key':manifest['run_key'],'counts':dict(counts),'target_approved_readback':approved,'processed':len(items)}))
