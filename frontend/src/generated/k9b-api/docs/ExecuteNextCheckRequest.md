
# ExecuteNextCheckRequest

Next-check execution request

## Properties

Name | Type
------------ | -------------
`candidateId` | string
`candidateIndex` | number
`clusterLabel` | string
`planArtifactPath` | string

## Example

```typescript
import type { ExecuteNextCheckRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "candidateId": null,
  "candidateIndex": null,
  "clusterLabel": null,
  "planArtifactPath": null,
} satisfies ExecuteNextCheckRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ExecuteNextCheckRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
