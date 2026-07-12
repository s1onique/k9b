
# ProbeAlertmanagerSourceRequest

AlertManager source probe request. sourceId is in body to keep the POST path stable regardless of the source identifier content.

## Properties

Name | Type
------------ | -------------
`sourceId` | string

## Example

```typescript
import type { ProbeAlertmanagerSourceRequest } from ''

// TODO: Update the object below with actual values
const example = {
  "sourceId": null,
} satisfies ProbeAlertmanagerSourceRequest

console.log(example)

// Convert the instance to a JSON string
const exampleJSON: string = JSON.stringify(example)
console.log(exampleJSON)

// Parse the JSON string back to an object
const exampleParsed = JSON.parse(exampleJSON) as ProbeAlertmanagerSourceRequest
console.log(exampleParsed)
```

[[Back to top]](#) [[Back to API list]](../README.md#api-endpoints) [[Back to Model list]](../README.md#models) [[Back to README]](../README.md)
