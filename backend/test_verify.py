from auth.password import verify_password

stored_hash = "$2b$12$Eh/JSnKG3qhtZEOzFFhMn.XgSMFbixedV3JakZyoXBWENNzgaEHeen"
result = verify_password("changeme", stored_hash)
print(f"Verification result for 'changeme' and stored hash: {result}")
