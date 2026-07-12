
# PerformAlertmanagerSourceActionRequest

AlertManager source action request. sourceId is in body to support slashes in identifiers.

## Properties

Name | Type
------------ | -------------
`action` | string
`clusterLabel` | string
`reason` | string
`sourceId` | string

## Example

```typescript
import type { PerformAlertmanagerSourceActionRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "action": null,
  "clusterLabel": null,
  "reason": null,
  "sourceId": null,
} satisfies PerformAlertmanagerSourceActionRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as PerformAlertmanagerSourceActionRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
