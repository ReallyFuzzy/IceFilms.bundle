Call StartFavouritesCheck(Wscript.Arguments)

Sub StartFavouritesCheck(args)
	
	If args.Count = 1 Then
		
		'Force the script to finish on an error.
		On Error Resume Next
	
		'Declare variables
		Dim objRequest
		Set objRequest = CreateObject("Microsoft.XMLHTTP")
	
		'Open the HTTP request and pass the URL to the objRequest object
		objRequest.open "GET", args(0), false
	
		'Send the HTML Request
		objRequest.Send
	
		Set objRequest = Nothing

	End If
	
End Sub