from backend.db import delete_all_visits
if __name__ == "__main__":
    confirm = input("Delete all saved demo visits? Type DELETE to continue: ")
    if confirm == "DELETE":
        delete_all_visits()
        print("All saved demo visits deleted.")
    else:
        print("Deletion cancelled.")
