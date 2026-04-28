import { sampleRun, sampleRunsList } from './fixtures';

console.log('=== Checking fixtures ===');
console.log('sampleRun.runId:', sampleRun?.runId);
console.log('deterministicNextChecks:', sampleRun?.deterministicNextChecks ? 'EXISTS' : 'NULL/UNDEFINED');
if (sampleRun?.deterministicNextChecks) {
  console.log('clusterCount:', sampleRun.deterministicNextChecks.clusterCount);
  console.log('clusters:', sampleRun.deterministicNextChecks.clusters?.length);
}
console.log('sampleRunsList first run:', sampleRunsList?.runs?.[0]?.runId);
